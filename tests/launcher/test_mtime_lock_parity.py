from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

# bootstrap.main -> bootstrap.webview2 -> `import winreg`, which only exists on Windows.
# Run this on the Windows target; skip elsewhere (the winreg fix that lets bootstrap
# import cross-platform is Slice 4). Matches tests/unit/test_migrate.py's precedent.
pytest.importorskip("winreg")

from bootstrap.config import LOCK_STALE_SECONDS  # noqa: E402
from bootstrap.main import _acquire_lock, _release_lock  # noqa: E402
from bootstrap.paths import AppPaths  # noqa: E402


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        root=tmp_path,
        python_dir=tmp_path / "python",
        app_dir=tmp_path / "app",
        state_dir=tmp_path / "state",
        logs_dir=tmp_path / "logs",
        marker_path=tmp_path / "state" / "bootstrap_marker.json",
        lock_path=tmp_path / "state" / "bootstrap.lock",
        browser_channel_path=tmp_path / "state" / "browser_channel.json",
        data_dir=tmp_path / "data",
    )


def test_lock_behavior_matches_legacy(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    assert _acquire_lock(paths) is True
    assert paths.lock_path.is_file()
    assert _acquire_lock(paths) is False  # fresh lock blocks a second acquire

    _release_lock(paths)
    assert not paths.lock_path.exists()
    _release_lock(paths)  # missing_ok -- must not raise on an already-released lock

    assert _acquire_lock(paths) is True
    stale_time = time.time() - LOCK_STALE_SECONDS - 1

    os.utime(paths.lock_path, (stale_time, stale_time))
    assert _acquire_lock(paths) is True  # stale lock is reclaimed, not honored
