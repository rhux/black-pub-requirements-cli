"""Frozen configuration (D6). ScheduleConfig replaces argparse.Namespace threading through
process_scout/async_main; both the CLI's argparse defaults and the local web UI's hand-built
config read their non-required field values from THIS module's dataclass defaults, so the two
call sites cannot drift apart the way a Namespace built by hand in two places already has
(ui.server's worker omits email_report; async_main's getattr(..., False) compensated for that
omission -- both go together in this task).

UiSettings (the local web UI's data-root resolution) lives here too, unchanged from its current
ui/server.py definition -- moved rather than duplicated, since `config` is a recognized layer in
the Phase B spec's dependency-edge table and a new sibling module would not be."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ScoutingMeritBadges"
DATA_DIR_ENV = "SCOUTMB_DATA_DIR"


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    input: Path
    sheet: str = "Scouts Only"
    output: Path = Path("scouting-output")
    headed: bool = False
    channel: str | None = None
    timeout: int = 45
    request_delay_ms: int = 200
    scout_delay_ms: int | None = None
    allow_dead_assets: bool = False
    include_adults: bool = False
    no_html: bool = False
    html_name: str = "report.html"
    email_report: bool = False


def _platform_data_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME / "data"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "data"
    return Path.home() / ".local" / "share" / APP_NAME / "data"


@dataclass(frozen=True, slots=True)
class UiSettings:
    """Where the local web UI reads/writes user data. NEVER derive a data path from __file__ --
    that ties irreplaceable data to the code's on-disk location, so moving or reinstalling
    silently relocates or destroys it."""

    data_root: Path

    @classmethod
    def resolve(cls, data_root: Path | None = None, dev_mode: bool = False) -> "UiSettings":
        if data_root is not None:
            return cls(Path(data_root))
        env = os.environ.get(DATA_DIR_ENV)
        if env:
            return cls(Path(env))
        if dev_mode:
            return cls(Path.cwd())
        return cls(_platform_data_root())

    @property
    def scouts_csv(self) -> Path:
        return self.data_root / "scouts.csv"

    @property
    def pdf_uploads_dir(self) -> Path:
        return self.data_root / "pdf-uploads"

    @property
    def runs_dir(self) -> Path:
        return self.data_root / "runs"

    def ensure_dirs(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
