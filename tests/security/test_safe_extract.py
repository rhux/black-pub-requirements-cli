from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from bootstrap.safe_extract import safe_extract_zip


def _make_zip(tmp_path: Path, name: str, entries: dict[str, bytes]) -> Path:
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as archive:
        for entry_name, data in entries.items():
            archive.writestr(entry_name, data)
    return zip_path


def test_hostile_archive_matrix(tmp_path: Path) -> None:
    dest = tmp_path / "extracted"

    traversal = _make_zip(tmp_path, "traversal.zip", {"../../evil.txt": b"x"})
    with pytest.raises(RuntimeError, match="traversal"):
        safe_extract_zip(traversal, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []

    absolute = _make_zip(tmp_path, "absolute.zip", {"/etc/evil.txt": b"x"})
    with pytest.raises(RuntimeError, match="absolute"):
        safe_extract_zip(absolute, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []

    oversized_zip = tmp_path / "oversized.zip"
    with zipfile.ZipFile(oversized_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.txt", b"0" * 1000)
    with pytest.raises(RuntimeError, match="expansion|budget"):
        safe_extract_zip(oversized_zip, dest, max_expanded_bytes=100)
    assert not dest.exists() or list(dest.rglob("*")) == []


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "extracted"
    zip_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3  # unix
        info.external_attr = 0o120777 << 16  # S_IFLNK
        archive.writestr(info, "/etc/passwd")

    with pytest.raises(RuntimeError, match="symlink"):
        safe_extract_zip(zip_path, dest)
    assert not dest.exists() or list(dest.rglob("*")) == []
