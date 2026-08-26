from __future__ import annotations

from pathlib import Path

from bootstrap.capability_cache import CacheManifest, evict_unreferenced, record_reference


def test_referenced_payloads_are_not_evicted(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    active_payload = cache_dir / "python-3.12.8.zip"
    rollback_payload = cache_dir / "python-3.12.7.zip"
    orphan_payload = cache_dir / "python-3.11.0.zip"
    for p in (active_payload, rollback_payload, orphan_payload):
        p.write_bytes(b"x")

    manifest = CacheManifest(entries={})
    manifest = record_reference(manifest, payload_id="python-3.12.8.zip", release_version="0.2.0")
    manifest = record_reference(manifest, payload_id="python-3.12.7.zip", release_version="0.1.0")

    evict_unreferenced(cache_dir, manifest, active_and_rollback_versions={"0.2.0", "0.1.0"})

    assert active_payload.exists()
    assert rollback_payload.exists()
    assert not orphan_payload.exists()
