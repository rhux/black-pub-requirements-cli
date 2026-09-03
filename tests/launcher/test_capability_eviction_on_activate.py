from __future__ import annotations

from pathlib import Path

from bootstrap import capability_cache, release
from bootstrap.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    root = tmp_path / "root"
    state_dir = root / "state"
    paths = AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=root / "app",
        state_dir=state_dir,
        logs_dir=root / "logs",
        marker_path=state_dir / "bootstrap_marker.json",
        lock_path=state_dir / "bootstrap.lock",
        browser_channel_path=state_dir / "browser_channel.json",
        data_dir=root / "data",
    )
    paths.ensure_dirs()
    return paths


def _fake_source_root(tmp_path: Path, version: str) -> Path:
    source = tmp_path / f"source-{version}"
    (source / "src" / "scoutmb").mkdir(parents=True)
    (source / "src" / "scoutmb" / "__init__.py").write_text("", encoding="utf-8")
    (source / "pyproject.toml").write_text(
        f'[project]\nname = "scoutmb"\nversion = "{version}"\n', encoding="utf-8"
    )
    (source / "requirements.txt").write_text("fastapi==0.1.0\n", encoding="utf-8")
    return source


def test_activate_evicts_capability_payloads_unreferenced_by_active_or_rollback(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    cache_dir = paths.capability_cache_dir
    ancient_payload = cache_dir / "chromium"
    ancient_payload.write_bytes(b"old-chromium")
    capability_cache.record_and_persist(cache_dir, payload_id="chromium", release_version="0.0.1")

    source_a = _fake_source_root(tmp_path, "0.1.0")
    manifest_a = release.stage_release(paths, source_a, source_a / "requirements.txt")
    release.activate(paths, manifest_a, state_generation=1)
    capability_cache.record_and_persist(cache_dir, payload_id="chromium", release_version="0.1.0")

    source_b = _fake_source_root(tmp_path, "0.2.0")
    manifest_b = release.stage_release(paths, source_b, source_b / "requirements.txt")
    release.activate(paths, manifest_b, state_generation=1)

    # 0.1.0 is now the rollback version (immediately prior to active 0.2.0) -- its chromium
    # reference must survive. 0.0.1 was never active/rollback at the point of THIS activation
    # and must be evicted.
    assert ancient_payload.exists() is False
