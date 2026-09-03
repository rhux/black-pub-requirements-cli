from __future__ import annotations

import subprocess
import sys


def test_bootstrap_main_is_importable_regardless_of_platform():
    """Regression test for the bug confirmed 2026-09-03: `import bootstrap.main` raised
    ModuleNotFoundError: No module named 'winreg' on macOS, because bootstrap/webview2.py did a
    module-level `import winreg`."""
    result = subprocess.run(
        [sys.executable, "-c", "import bootstrap.main"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_webview2_module_itself_is_importable_standalone():
    result = subprocess.run(
        [sys.executable, "-c", "import bootstrap.webview2"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
