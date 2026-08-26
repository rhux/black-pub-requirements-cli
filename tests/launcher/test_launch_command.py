from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# bootstrap.main -> bootstrap.webview2 -> `import winreg`, which only exists on Windows.
# Run this on the Windows target; skip elsewhere (the winreg fix that lets bootstrap
# import cross-platform is Slice 4). Matches tests/unit/test_migrate.py's precedent.
pytest.importorskip("winreg")

from bootstrap import release as release_module  # noqa: E402
from bootstrap.main import _launch_app  # noqa: E402
from bootstrap.paths import AppPaths  # noqa: E402


def _fake_source_root(tmp_path: Path, version: str) -> Path:
    source = tmp_path / f"source-{version}"
    (source / "src" / "scoutmb").mkdir(parents=True)
    (source / "src" / "scoutmb" / "__init__.py").write_text("", encoding="utf-8")
    (source / "pyproject.toml").write_text(
        f'[project]\nname = "scoutmb"\nversion = "{version}"\n', encoding="utf-8"
    )
    (source / "requirements.txt").write_text("fastapi==0.1.0\n", encoding="utf-8")
    return source


def test_launch_uses_active_release_dir_as_cwd_after_staging(
    tmp_path: Path, monkeypatch
) -> None:
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
    source = _fake_source_root(tmp_path, "0.1.0")
    manifest = release_module.stage_release(paths, source, source / "requirements.txt")
    release_module.activate(paths, manifest, state_generation=1)

    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["cwd"] = kwargs.get("cwd")
        return MagicMock()

    monkeypatch.setattr("bootstrap.main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("bootstrap.main.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "bootstrap.main.python_env.pythonw_exe", lambda p: Path("/fake/pythonw.exe")
    )

    _launch_app(paths, channel=None)

    expected_cwd = str(release_module.active_app_dir(paths))
    assert captured["cwd"] == expected_cwd
    # Proves this is actually exercising the versioned release dir, not the
    # static app_dir the two happen to share a parent with.
    assert captured["cwd"] != str(paths.app_dir)


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
