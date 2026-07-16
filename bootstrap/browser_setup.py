"""Choose and provision a browser for Playwright: prefer the system's
Microsoft Edge (near-zero extra download), fall back to Playwright's own
bundled Chromium only if that doesn't work.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from bootstrap.paths import AppPaths
from bootstrap.python_env import python_exe

ProgressFn = Callable[[str], None]

PROBE_TIMEOUT_SECONDS = 20
CHROMIUM_INSTALL_TIMEOUT_SECONDS = 20 * 60


def _log(log: ProgressFn | None, message: str) -> None:
    if log is not None:
        log(message)


def probe_msedge_channel(paths: AppPaths) -> bool:
    if os.environ.get("SCOUTMB_FORCE_CHROMIUM_FALLBACK"):
        return False  # test-only escape hatch, inert unless explicitly set

    probe_path = paths.app_dir / "_bootstrap_support" / "probe_msedge.py"
    try:
        result = subprocess.run(
            [str(python_exe(paths)), str(probe_path)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def install_chromium_fallback(paths: AppPaths, log: ProgressFn | None = None) -> None:
    _log(log, "Downloading browser (this can take a few minutes)...")
    result = subprocess.run(
        [str(python_exe(paths)), "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=CHROMIUM_INSTALL_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Chromium install failed:\n{result.stdout}\n{result.stderr}")


def resolve_browser_channel(paths: AppPaths, log: ProgressFn | None = None) -> str | None:
    """Returns the Playwright channel to use, or None to use bundled Chromium."""
    _log(log, "Checking browser...")
    if probe_msedge_channel(paths):
        return "msedge"
    install_chromium_fallback(paths, log)
    return None


def write_browser_channel_marker(paths: AppPaths, channel: str | None) -> None:
    paths.browser_channel_path.write_text(json.dumps({"channel": channel}), encoding="utf-8")


def read_browser_channel_marker(paths: AppPaths) -> str | None:
    try:
        data = json.loads(paths.browser_channel_path.read_text(encoding="utf-8"))
        return data.get("channel")
    except (OSError, json.JSONDecodeError):
        return None
