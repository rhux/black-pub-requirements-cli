"""A local, in-memory stand-in for wherever capability payloads would eventually be hosted.
No network -- proves the staging/resume/update contract without needing a real hosted channel,
which stays POSTPONED per Slice 4's descope reminders."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from bootstrap import capability_cache


@dataclass
class InstallResult:
    completed: bool


class LocalCapabilitySource:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._payloads: dict[str, tuple[str, bytes]] = {}
        self._fail_next: set[str] = set()
        self._offline = False
        self.download_call_counter: Counter[str] = Counter()

    def add_payload(self, payload_id: str, *, version: str, contents: bytes) -> None:
        self._payloads[payload_id] = (version, contents)

    def fail_next_download(self, payload_id: str) -> None:
        self._fail_next.add(payload_id)

    def go_offline(self) -> None:
        self._offline = True

    def reset_download_call_counter(self) -> Counter[str]:
        prior = self.download_call_counter
        self.download_call_counter = Counter()
        return prior

    def _versioned_dest(self, cache_dir: Path, payload_id: str, version: str) -> Path:
        # Immutable per-version path -- a payload already staged for THIS version is never
        # re-fetched, but a new version never collides with (or is masked by) an old one.
        return cache_dir / f"{payload_id}-{version}"

    def install_one(self, *, cache_dir: Path, release_version: str, payload_id: str) -> None:
        version, contents = self._payloads[payload_id]
        dest = self._versioned_dest(cache_dir, payload_id, version)
        if dest.exists():
            capability_cache.record_and_persist(
                cache_dir, payload_id=payload_id, release_version=release_version
            )
            return  # already staged and verified -- never re-fetched

        if payload_id in self._fail_next:
            self._fail_next.discard(payload_id)
            raise RuntimeError(f"simulated failure downloading {payload_id}")

        source_file = self.root / f"{payload_id}-{version}.bin"
        source_file.write_bytes(contents)
        self.download_call_counter[payload_id] += 1

        dest.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest.with_suffix(dest.suffix + ".part")
        part_path.write_bytes(contents)
        part_path.replace(dest)  # atomic -- a killed download never leaves a file at dest

        capability_cache.record_and_persist(
            cache_dir, payload_id=payload_id, release_version=release_version
        )

    def install_all(self, *, cache_dir: Path, release_version: str) -> InstallResult:
        for payload_id in self._payloads:
            try:
                self.install_one(
                    cache_dir=cache_dir, release_version=release_version, payload_id=payload_id
                )
            except RuntimeError:
                return InstallResult(completed=False)
        return InstallResult(completed=True)

    def can_launch_from_cache(self, *, cache_dir: Path, release_version: str) -> bool:
        if self._offline:
            return all(
                self._versioned_dest(cache_dir, payload_id, version).exists()
                for payload_id, (version, _contents) in self._payloads.items()
            )
        return True
