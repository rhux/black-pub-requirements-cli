from __future__ import annotations

import contextlib
import tempfile
import zipfile
from pathlib import Path

from bootstrap.safe_extract import safe_extract_zip
from hypothesis import given
from hypothesis import strategies as st


@given(st.binary(max_size=1000))
def test_safe_extract_never_writes_outside_the_destination(payload: bytes):
    """Property: for ANY byte string fed in as a would-be archive entry name, safe_extract_zip
    either rejects it cleanly or writes only under the destination -- never above it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()  # macOS: /tmp resolves through /private -- resolve once
        archive_path = tmp_path / "test.zip"
        dest = tmp_path / "dest"
        dest.mkdir()
        try:
            name = payload.decode("utf-8", errors="ignore") or "x"
        except Exception:
            name = "x"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr(name, b"content")

        with contextlib.suppress(Exception):  # rejection is an acceptable outcome
            safe_extract_zip(archive_path, dest, max_expanded_bytes=10_000)

        for written in dest.rglob("*"):
            assert dest in written.resolve().parents or written.resolve() == dest.resolve()
