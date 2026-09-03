from __future__ import annotations

import http.server
import shutil
import sys
import threading
from pathlib import Path

import pytest
from bootstrap.paths import AppPaths

REPO_ROOT = Path(__file__).resolve().parents[2]


def _paths_with_bundled_probe(tmp_path: Path) -> AppPaths:
    """A real AppPaths whose _bootstrap_support dir actually contains probe_readiness.py, the
    way a real install's app_dir would -- verify_readiness subprocesses out to this file."""
    root = tmp_path / "root"
    state_dir = root / "state"
    app_dir = root / "app"
    support_dir = app_dir / "_bootstrap_support"
    support_dir.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "bootstrap" / "probe_readiness.py", support_dir / "probe_readiness.py")

    paths = AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=app_dir,
        state_dir=state_dir,
        logs_dir=root / "logs",
        marker_path=state_dir / "bootstrap_marker.json",
        lock_path=state_dir / "bootstrap.lock",
        browser_channel_path=state_dir / "browser_channel.json",
        data_dir=root / "data",
    )
    paths.ensure_dirs()
    return paths


@pytest.fixture
def loopback_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join(timeout=5)


@pytest.mark.playwright
def test_selected_engine_completes_local_fake_flow(tmp_path, monkeypatch, loopback_server):
    from bootstrap import browser_setup

    # This dev environment's own interpreter has playwright + chromium installed -- use it as
    # the stand-in for the provisioned embedded Python that a real install would have.
    monkeypatch.setattr(browser_setup, "python_exe", lambda paths: Path(sys.executable))
    paths = _paths_with_bundled_probe(tmp_path)

    port = loopback_server.server_address[1]
    assert browser_setup.verify_readiness(paths, channel=None, url=f"http://127.0.0.1:{port}/")


@pytest.mark.playwright
def test_readiness_failure_does_not_switch_engines(tmp_path, monkeypatch):
    from bootstrap import browser_setup

    monkeypatch.setattr(browser_setup, "python_exe", lambda paths: Path(sys.executable))
    paths = _paths_with_bundled_probe(tmp_path)

    calls: list[str] = []
    monkeypatch.setattr(
        browser_setup, "install_chromium_capability", lambda *a, **k: calls.append("switched")
    )

    # Port 1 is a privileged/unused port -- connecting there fails fast and reliably.
    ok = browser_setup.verify_readiness(paths, channel=None, url="http://127.0.0.1:1/")

    assert ok is False
    assert calls == []  # a readiness failure is reported, never silently worked around


def test_verify_readiness_never_imports_playwright_in_this_process():
    """The regression this whole redesign exists to prevent: importing bootstrap.browser_setup
    must never pull in playwright, or PyInstaller's Analysis bundles it into the frozen
    installer (confirmed via a real build: ~52MB vs. an 18MB budget)."""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import bootstrap.browser_setup, sys; "
            "assert 'playwright' not in sys.modules, sys.modules.keys()",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
