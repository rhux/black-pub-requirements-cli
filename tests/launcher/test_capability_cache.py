from __future__ import annotations

from pathlib import Path

from bootstrap import capability_cache
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


def test_evict_unreferenced_never_deletes_the_manifest_file_itself(tmp_path: Path) -> None:
    """Regression: manifest.json lives inside cache_dir (capability_cache.save's location) --
    the same directory evict_unreferenced scans for orphaned payloads. Since "manifest.json" is
    never itself a recorded payload_id, a naive scan would delete it as "unreferenced" on every
    activation, silently wiping all cache-reference history."""
    cache_dir = tmp_path / "cache"
    capability_cache.record_and_persist(cache_dir, payload_id="chromium", release_version="1.0.0")

    manifest = capability_cache.load(cache_dir)
    evict_unreferenced(cache_dir, manifest, active_and_rollback_versions={"1.0.0"})

    assert (cache_dir / "manifest.json").exists()


def test_evict_unreferenced_tolerates_a_cache_dir_that_was_never_created(tmp_path: Path) -> None:
    """A first activation before anything has ever been staged into capability_cache_dir must
    not crash -- consistent with load()'s own handling of a missing directory."""
    never_created = tmp_path / "cache"

    evict_unreferenced(never_created, CacheManifest(), active_and_rollback_versions={"1.0.0"})
