"""Preflights free disk space before a download/extraction/staging sequence starts, so a
disk-full condition is caught before any bytes are written, not discovered mid-write."""

from __future__ import annotations

import shutil
from pathlib import Path


def preflight_disk_space(root: Path, required_bytes: int) -> None:
    usage = shutil.disk_usage(root)
    if usage.free < required_bytes:
        raise RuntimeError(
            f"insufficient disk space at {root}: free={usage.free} required={required_bytes}"
        )
