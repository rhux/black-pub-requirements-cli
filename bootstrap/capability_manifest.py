"""Hash/version/OS/arch binding for one downloaded capability payload (embeddable Python zip,
browser binary) -- the payload-level analogue of bootstrap/release_manifest.py::ReleaseManifest,
which only ever bound the app *source*, never a platform-specific compiled artifact."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityManifest:
    """sha256/size_bytes are None for a payload we don't acquire via our own downloader (e.g.
    Chromium, acquired through Playwright's own installer) -- there is nothing of ours to pin
    a hash against, so the field is optional rather than forcing a second manifest shape."""

    payload_id: str
    version: str
    os: str
    arch: str
    source_url: str
    sha256: str | None = None
    size_bytes: int | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "payload_id": self.payload_id,
                "version": self.version,
                "os": self.os,
                "arch": self.arch,
                "sha256": self.sha256,
                "size_bytes": self.size_bytes,
                "source_url": self.source_url,
            }
        )

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CapabilityManifest:
        return cls(**data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_capability_manifest(
    *, payload_id: str, version: str, source_url: str, payload_path: Path
) -> CapabilityManifest:
    return CapabilityManifest(
        payload_id=payload_id,
        version=version,
        os=platform.system(),
        arch=platform.machine(),
        sha256=_sha256(payload_path),
        size_bytes=payload_path.stat().st_size,
        source_url=source_url,
    )
