"""Chunked, resumable-safe file download using only the standard library."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Callable

CHUNK_SIZE = 64 * 1024


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        from urllib.parse import urlparse

        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self._allowed_hosts:
            raise RuntimeError(
                f"Refusing redirect to untrusted target: {newurl!r} "
                f"(allowed hosts: {sorted(self._allowed_hosts)})"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(
    url: str,
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    allowed_redirect_hosts: frozenset[str] | None = None,
) -> None:
    """Download `url` to `dest`, atomically (a killed download never leaves a file at `dest`).
    When expected_sha256/expected_size are given, the downloaded file is validated against both
    before the atomic rename -- a mismatch deletes the partial download and raises, never leaves
    a corrupt or tampered file at `dest`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_suffix(dest.suffix + ".part")

    from urllib.parse import urlparse

    source_host = urlparse(url).hostname
    hosts = allowed_redirect_hosts or (frozenset({source_host}) if source_host else frozenset())
    opener = urllib.request.build_opener(_AllowlistRedirectHandler(hosts))

    request = urllib.request.Request(url, headers={"User-Agent": "ScoutingMeritBadges-Bootstrapper"})
    digest = hashlib.sha256()
    with opener.open(request, timeout=30) as response:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with part_path.open("wb") as stream:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                stream.write(chunk)
                digest.update(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(written, total)

    if expected_size is not None and written != expected_size:
        part_path.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded size mismatch for {url}: expected={expected_size} got={written}")
    if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
        part_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"downloaded sha256 mismatch for {url}: expected={expected_sha256} got={digest.hexdigest()}"
        )

    os.replace(part_path, dest)
