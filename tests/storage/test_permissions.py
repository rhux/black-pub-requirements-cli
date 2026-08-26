from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from scoutmb.config import UiSettings


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_current_user_permissions_on_supported_platforms(tmp_path: Path) -> None:
    settings = UiSettings(data_root=tmp_path / "data")
    settings.ensure_dirs()

    settings.apply_private_permissions()

    mode = stat.S_IMODE(settings.data_root.stat().st_mode)
    assert mode == 0o700


@pytest.mark.skipif(sys.platform != "win32", reason="documents the Windows no-op")
def test_windows_apply_private_permissions_is_a_documented_noop(tmp_path: Path) -> None:
    settings = UiSettings(data_root=tmp_path / "data")
    settings.ensure_dirs()

    settings.apply_private_permissions()  # must not raise; ACLs are POSTPONED
