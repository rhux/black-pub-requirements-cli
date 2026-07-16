"""Re-sync this app's source into the app-local folder on every launch.

This is a targeted overwrite of an explicit allowlist, never a directory
wipe — scouts.csv, pdf-uploads/, and runs/ live in the same app\\ folder as
user data and must survive untouched across re-syncs.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from bootstrap.paths import AppPaths

# (relative source path, is_directory)
_FILES = [
    "run_app.py",
    "pdf_to_scouts.py",
    "scout_schedule_cli.py",
    "requirements.txt",
    "ui/__init__.py",
    "ui/server.py",
]
_DIRS = [
    "ui/static",
]


def _source_root() -> Path:
    """Where the bundled app source lives: PyInstaller's temp extraction dir
    when frozen, or the real repo root when running unfrozen for local testing.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app_src"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _probe_msedge_source() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app_src" / "_bootstrap_support" / "probe_msedge.py"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "probe_msedge.py"


def sync_app_source(paths: AppPaths) -> None:
    source_root = _source_root()

    for relative in _FILES:
        src = source_root / relative
        dest = paths.app_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    for relative in _DIRS:
        src = source_root / relative
        dest = paths.app_dir / relative
        shutil.copytree(src, dest, dirs_exist_ok=True)

    support_dest = paths.app_dir / "_bootstrap_support" / "probe_msedge.py"
    support_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_probe_msedge_source(), support_dest)
