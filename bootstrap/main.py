"""Orchestrates the bootstrap sequence: check marker -> provision -> sync -> launch."""

from __future__ import annotations

import logging
import os
import subprocess
import time
import traceback

from bootstrap import browser_setup, marker, python_env, source_sync, webview2
from bootstrap.config import LOCK_STALE_SECONDS
from bootstrap.paths import AppPaths, get_paths
from bootstrap.ui import ProgressWindow

APP_LAUNCH_SETTLE_SECONDS = 2


def _setup_logging(paths: AppPaths) -> logging.Logger:
    paths.ensure_dirs()
    logger = logging.getLogger("bootstrap")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(paths.logs_dir / "bootstrap.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def _acquire_lock(paths: AppPaths) -> bool:
    if paths.lock_path.exists():
        age = time.time() - paths.lock_path.stat().st_mtime
        if age < LOCK_STALE_SECONDS:
            return False
        paths.lock_path.unlink(missing_ok=True)
    try:
        paths.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(paths.lock_path, "x"):
            pass
        return True
    except FileExistsError:
        return False


def _release_lock(paths: AppPaths) -> None:
    paths.lock_path.unlink(missing_ok=True)


def _launch_app(paths: AppPaths, channel: str | None) -> None:
    log_path = paths.logs_dir / "run_app.log"
    env = {**os.environ, "SCOUTMB_BROWSER_CHANNEL": channel or ""}
    with open(log_path, "ab") as log_fh:
        subprocess.Popen(
            [str(python_env.pythonw_exe(paths)), str(paths.app_dir / "run_app.py")],
            cwd=str(paths.app_dir),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
    # Give the child process a moment to get its own window up before this
    # window disappears, so the friend never sees "nothing happening."
    time.sleep(APP_LAUNCH_SETTLE_SECONDS)


def _run(window: ProgressWindow, paths: AppPaths, logger: logging.Logger) -> None:
    requirements_path = paths.app_dir / "requirements.txt"

    def status(text: str) -> None:
        logger.info(text)
        window.set_status(text)

    status("Checking previous setup...")
    source_sync.sync_app_source(paths)

    if marker.is_environment_valid(paths, requirements_path):
        status("Starting application...")
        channel = browser_setup.read_browser_channel_marker(paths)
        _launch_app(paths, channel)
        window.finish()
        return

    status("Setting up Python environment (first run only, may take a few minutes)...")
    python_env.provision_python(paths, requirements_path, log=status)

    status("Checking browser...")
    webview2.ensure_webview2(log=status)
    channel = browser_setup.resolve_browser_channel(paths, log=status)
    browser_setup.write_browser_channel_marker(paths, channel)

    marker.write_marker(
        paths,
        requirements_hash=marker.compute_requirements_hash(requirements_path),
        browser_channel=channel,
    )

    status("Starting application...")
    _launch_app(paths, channel)
    window.finish()


def main() -> int:
    paths = get_paths()
    logger = _setup_logging(paths)
    window = ProgressWindow("Scouting Merit Badges - Setup")

    if not _acquire_lock(paths):
        window.run(
            lambda: window.fail(
                "Setup already running",
                "Setup appears to already be running. Please wait a few minutes and try again.",
            )
        )
        return 1

    def worker() -> None:
        try:
            _run(window, paths, logger)
        except Exception as exc:  # noqa: BLE001 - surfaced to the friend, never a raw traceback
            logger.error("Bootstrap failed: %s\n%s", exc, traceback.format_exc())
            window.fail(
                "Setup failed",
                f"Something went wrong while setting up:\n\n{exc}\n\n"
                f"Details were saved to:\n{paths.logs_dir / 'bootstrap.log'}",
            )
        finally:
            _release_lock(paths)

    window.run(worker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
