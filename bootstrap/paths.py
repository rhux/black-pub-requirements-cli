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
    data_dir: Path

    @property
    def releases_dir(self) -> Path:
        return self.root / "releases"

    @property
    def current_pointer_path(self) -> Path:
        return self.state_dir / "current.json"

    def ensure_dirs(self) -> None:
        for path in (
            self.root,
            self.python_dir,
            self.app_dir,
            self.state_dir,
            self.logs_dir,
            self.releases_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def resolve_root() -> Path:
    override = os.environ.get("SCOUTMB_BOOTSTRAP_ROOT")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError(
            "Cannot resolve the bootstrap root: LOCALAPPDATA is not set and "
            "SCOUTMB_BOOTSTRAP_ROOT was not provided as an override. On a real Windows "
            "install LOCALAPPDATA is always set by the OS; set SCOUTMB_BOOTSTRAP_ROOT "
            "explicitly when running off Windows (tests, macOS development)."
        )
    return Path(base) / APP_NAME


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
        data_dir=root / "data",
    )
