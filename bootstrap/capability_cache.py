"""Reference-counted eviction for downloaded capability payloads (Python embeddable zip,
browser installers, PDF-support wheels). A payload is evicted only when neither the active nor
the immediately-prior (rollback) release manifest still references it -- Task C7's transactional
install is what keeps two release manifests around at once."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True, slots=True)
class CacheManifest:
    entries: dict[str, list[str]] = field(default_factory=dict)  # payload_id -> [release_version, ...]


def load(cache_dir: Path) -> CacheManifest:
    manifest_path = cache_dir / _MANIFEST_FILE
    if not manifest_path.exists():
        return CacheManifest()
    return CacheManifest(entries=json.loads(manifest_path.read_text(encoding="utf-8"))["entries"])


def save(cache_dir: Path, manifest: CacheManifest) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / _MANIFEST_FILE).write_text(
        json.dumps({"entries": manifest.entries}), encoding="utf-8"
    )


def record_and_persist(cache_dir: Path, *, payload_id: str, release_version: str) -> None:
    """Load-record-save in one step -- the shape every real call site (python_env.py,
    browser_setup.py) needs; record_reference alone is kept pure/standalone for the unit test
    above and for evict_unreferenced's manifest-in/manifest-out shape."""
    updated = record_reference(load(cache_dir), payload_id=payload_id, release_version=release_version)
    save(cache_dir, updated)


def record_reference(manifest: CacheManifest, *, payload_id: str, release_version: str) -> CacheManifest:
    entries = {k: list(v) for k, v in manifest.entries.items()}
    entries.setdefault(payload_id, [])
    if release_version not in entries[payload_id]:
        entries[payload_id].append(release_version)
    return CacheManifest(entries=entries)


def evict_unreferenced(
    cache_dir: Path, manifest: CacheManifest, active_and_rollback_versions: set[str]
) -> None:
    """Iterates the actual cache directory, not manifest.entries -- a payload the manifest
    never recorded a reference for at all is just as unreferenced as one whose only recorded
    references are stale, and must be evicted the same way."""
    for payload_path in cache_dir.iterdir():
        if not payload_path.is_file() or payload_path.name == _MANIFEST_FILE:
            continue
        referenced_by = manifest.entries.get(payload_path.name, [])
        still_referenced = any(v in active_and_rollback_versions for v in referenced_by)
        if not still_referenced:
            payload_path.unlink(missing_ok=True)
