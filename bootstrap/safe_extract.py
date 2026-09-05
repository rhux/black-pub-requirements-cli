"""ZIP extraction hardened against the standard hostile-archive matrix: path traversal,
absolute paths, symlink entries, and expansion (zip-bomb) attacks. Used everywhere
bootstrap/ extracts a downloaded archive -- never call zipfile.ZipFile.extractall directly."""

from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

_SYMLINK_MODE = 0o120000  # S_IFLNK, as stored in the top 16 bits of external_attr


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return (mode & 0xF000) == _SYMLINK_MODE


# 100MB: ~9x the real measured size of this codebase's one actual caller's payload -- the
# python-embed.zip python_env.py downloads is 11,094,114 bytes (measured 2026-09-03, see
# bootstrap/config.py::PYTHON_EMBED_SHA256's provenance comment) -- with headroom for a future
# larger embeddable Python release. Previously a guessed, unmeasured 2GB placeholder (Slice 4,
# D7: "every limit must be a real measured value").
_DEFAULT_MAX_EXPANDED_BYTES = 100_000_000


def safe_extract_zip(
    zip_path: Path, dest: Path, *, max_expanded_bytes: int = _DEFAULT_MAX_EXPANDED_BYTES
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        total_expanded = 0
        for info in archive.infolist():
            name = info.filename
            pure = PurePosixPath(name)
            if pure.is_absolute():
                raise RuntimeError(f"refusing absolute path entry in archive: {name!r}")
            if ".." in pure.parts:
                raise RuntimeError(f"refusing path-traversal entry in archive: {name!r}")
            if _is_symlink_entry(info):
                raise RuntimeError(f"refusing symlink entry in archive: {name!r}")
            total_expanded += info.file_size
            if total_expanded > max_expanded_bytes:
                raise RuntimeError(
                    f"archive expansion budget exceeded: {total_expanded} > {max_expanded_bytes}"
                )
        # Only after every entry in the archive has passed every check does extraction begin --
        # a hostile entry anywhere in the archive must leave nothing written to dest at all.
        archive.extractall(dest)
