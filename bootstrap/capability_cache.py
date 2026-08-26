"""Reference-counted eviction for downloaded capability payloads (Python embeddable zip,
browser installers, PDF-support wheels). A payload is evicted only when neither the active nor
the immediately-prior (rollback) release manifest still references it -- Task C7's transactional
install is what keeps two release manifests around at once."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CacheManifest:
    entries: dict[str, list[str]] = field(default_factory=dict)  # payload_id -> [release_version, ...]


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
        if not payload_path.is_file():
            continue
        referenced_by = manifest.entries.get(payload_path.name, [])
        still_referenced = any(v in active_and_rollback_versions for v in referenced_by)
        if not still_referenced:
            payload_path.unlink(missing_ok=True)
