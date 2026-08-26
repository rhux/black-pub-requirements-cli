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


def safe_extract_zip(zip_path: Path, dest: Path, *, max_expanded_bytes: int = 2 * 1024**3) -> None:
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
