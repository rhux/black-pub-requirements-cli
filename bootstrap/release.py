"""Transactional release install: stage into a fresh versioned directory, validate durable-state
compatibility, and atomically switch current.json -- replacing source_sync.sync_app_source's
direct in-place copy, which the spec names as "temporary... the transactional payload install
replaces it." The currently-active release is never mutated; a failed candidate is left staged
(not deleted) so a retry doesn't recopy from scratch, and current.json is never written except
by activate(), via the same .tmp + os.replace pattern bootstrap/marker.py already uses."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from bootstrap.activation import ActivationTuple, validate_activation
from bootstrap.paths import AppPaths
from bootstrap.release_manifest import ReleaseManifest, build_release_manifest

_MANIFEST_FILE = "release_manifest.json"
_STAGED_MARKER = ".staged"


def stage_release(paths: AppPaths, source_root: Path, requirements_path: Path) -> ReleaseManifest:
    manifest = build_release_manifest(source_root, requirements_path)
    release_dir = paths.releases_dir / manifest.version
    marker_path = release_dir / _STAGED_MARKER
    if marker_path.is_file():
        return manifest  # already fully staged -- idempotent, no re-copy

    if release_dir.exists():
        shutil.rmtree(release_dir)  # a prior PARTIAL stage is never trusted, always redone
    release_dir.mkdir(parents=True)

    shutil.copytree(source_root / "src" / "scoutmb", release_dir / "scoutmb")
    shutil.copy2(requirements_path, release_dir / "requirements.txt")
    (release_dir / _MANIFEST_FILE).write_text(
        json.dumps(manifest.to_json(), indent=2), encoding="utf-8"
    )
    marker_path.write_text("", encoding="utf-8")  # written last -- marks staging complete
    return manifest


def activate(paths: AppPaths, manifest: ReleaseManifest, *, state_generation: int) -> None:
    if not validate_activation(manifest, state_generation):
        raise RuntimeError(
            f"refusing activation: release {manifest.version} cannot read durable-state "
            f"generation {state_generation} (supports "
            f"[{manifest.state_schema_min}, {manifest.state_schema_max}])"
        )
    tuple_ = ActivationTuple(
        release_version=manifest.version,
        state_generation=state_generation,
        capability_manifest_digest=manifest.requirements_hash,
    )
    tmp_path = paths.current_pointer_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(tuple_.to_json(), indent=2), encoding="utf-8")
    os.replace(tmp_path, paths.current_pointer_path)


def current_release_version(paths: AppPaths) -> str | None:
    if not paths.current_pointer_path.is_file():
        return None
    data = json.loads(paths.current_pointer_path.read_text(encoding="utf-8"))
    return ActivationTuple.from_json(data).release_version


def active_app_dir(paths: AppPaths) -> Path:
    version = current_release_version(paths)
    if version is None:
        raise RuntimeError("no release is currently active (current.json missing)")
    return paths.releases_dir / version / "scoutmb"
