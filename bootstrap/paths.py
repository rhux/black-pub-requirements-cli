"""Filesystem layout for the bootstrapped app-local environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from bootstrap.config import APP_NAME


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    python_dir: Path
    app_dir: Path
    state_dir: Path
    logs_dir: Path
    marker_path: Path
    lock_path: Path
    browser_channel_path: Path

    def ensure_dirs(self) -> None:
        for path in (self.root, self.python_dir, self.app_dir, self.state_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


def resolve_root() -> Path:
    override = os.environ.get("SCOUTMB_BOOTSTRAP_ROOT")
    if override:
        return Path(override)
    return Path(os.environ["LOCALAPPDATA"]) / APP_NAME


def get_paths() -> AppPaths:
    root = resolve_root()
    state_dir = root / "state"
    return AppPaths(
        root=root,
        python_dir=root / "python",
        app_dir=root / "app",
        state_dir=state_dir,
        logs_dir=root / "logs",
        marker_path=state_dir / "bootstrap_marker.json",
        lock_path=state_dir / "bootstrap.lock",
        browser_channel_path=state_dir / "browser_channel.json",
    )
