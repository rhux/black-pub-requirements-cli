"""Chunked, resumable-safe file download using only the standard library."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Callable

CHUNK_SIZE = 64 * 1024


def download(url: str, dest: Path, on_progress: Callable[[int, int], None] | None = None) -> None:
    """Download `url` to `dest`, atomically (a killed download never leaves a file at `dest`)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_suffix(dest.suffix + ".part")

    request = urllib.request.Request(url, headers={"User-Agent": "ScoutingMeritBadges-Bootstrapper"})
    with urllib.request.urlopen(request, timeout=30) as response:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with part_path.open("wb") as stream:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                stream.write(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(written, total)

    os.replace(part_path, dest)
