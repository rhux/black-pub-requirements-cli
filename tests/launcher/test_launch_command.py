from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# bootstrap.main -> bootstrap.webview2 -> `import winreg`, which only exists on Windows.
# Run this on the Windows target; skip elsewhere (the winreg fix that lets bootstrap
# import cross-platform is Slice 4). Matches tests/unit/test_migrate.py's precedent.
pytest.importorskip("winreg")

from bootstrap.main import _launch_app  # noqa: E402
from bootstrap.paths import AppPaths  # noqa: E402


def test_launch_uses_the_real_desktop_entrypoint_module(tmp_path: Path, monkeypatch) -> None:
    paths = AppPaths(
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
    paths.ensure_dirs()
    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return MagicMock()

    monkeypatch.setattr("bootstrap.main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("bootstrap.main.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "bootstrap.main.python_env.pythonw_exe", lambda p: Path("/fake/pythonw.exe")
    )

    _launch_app(paths, channel=None)

    argv = captured["argv"]
    assert argv[0] == "/fake/pythonw.exe" or str(argv[0]) == "/fake/pythonw.exe"
    assert argv[1:] == ["-m", "scoutmb.interfaces.desktop.app"]
    # And the module this argv names must actually exist and import cleanly today --
    # the whole point of this test is catching a repeat of the run_app.py regression.
    importlib.import_module("scoutmb.interfaces.desktop.app")
