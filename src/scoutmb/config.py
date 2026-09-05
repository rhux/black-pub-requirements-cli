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
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ScoutingMeritBadges"

_PRIVATE_DIR_MODE = 0o700
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
    # Consecutive scout-fetch failures before the acquisition circuit breaker opens (D22/B10.2)
    # -- the legacy CLI had no breaker at all, so there is no prior value to preserve.
    breaker_threshold: int = 5


def _directory_size(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def _delete_directory_contents(root: Path) -> None:
    """Removes root itself if present, then recreates it empty -- callers never see a
    missing directory, only an empty one, so downstream code that assumes the dir exists
    keeps working."""
    if root.is_dir():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


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
    def resolve(cls, data_root: Path | None = None, dev_mode: bool = False) -> UiSettings:
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

    def apply_private_permissions(self) -> None:
        """Best-effort current-user-only permissions. POSIX: chmod 0700. Windows: a
        documented no-op -- ACL-based restriction is POSTPONED (vNext), not silently
        claimed here."""
        if sys.platform == "win32":
            return
        self.data_root.chmod(_PRIVATE_DIR_MODE)

    def category_sizes(self) -> dict[str, int]:
        return {
            "scouts_csv": _file_size(self.scouts_csv),
            "pdf_uploads": _directory_size(self.pdf_uploads_dir),
            "runs": _directory_size(self.runs_dir),
        }

    def delete_category(self, category: str) -> None:
        targets = {
            "pdf_uploads": self.pdf_uploads_dir,
            "runs": self.runs_dir,
        }
        target = targets.get(category)
        if target is None:
            return
        _delete_directory_contents(target)


@dataclass(frozen=True, slots=True)
class ReleaseLimits:
    """Every field's default is a MEASURED value (Slice 4, D7), not a guessed round number.
    Measured 2026-09-05 against a real 200-page synthetic PDF (tests/factories/pdf_builder,
    run through the real scoutmb.adapters.pdf.pages.extract_pdf): 2,419,811 bytes on disk,
    3.125s wall time, ~133MB real OS-level max RSS (resource.getrusage -- tracemalloc alone
    showed only 730KB, since it never sees fitz/cv2/numpy's native buffers). Rendered-page
    pixel dimensions measured directly via fitz at each DPI tier this app actually uses; a US
    Letter page at 400 DPI (the highest tier) is 3400x4400px.

    max_workers/max_queue_depth/disk_reserve_bytes/startup_timeout_seconds/
    max_requests_per_run, all present in earlier drafts of this dataclass, were dropped: this
    package processes attendees strictly sequentially (no worker pool, no request queue), and
    no code path anywhere caps concurrent requests or preflights disk space against a runtime
    budget -- including them with fabricated numbers would violate "every field must be a real
    measured value." max_archive_bytes was also dropped from here: scoutmb has zero zipfile/
    archive handling anywhere (grepped to confirm) -- the one real "archive extraction with an
    unmeasured limit" in this codebase is bootstrap/safe_extract.py::safe_extract_zip, a
    bootstrap-layer concern (bootstrap deliberately never imports scoutmb) fixed at its own
    real call site instead.

    Re-run the measurement (tests/performance/test_resource_limits.py documents the exact
    commands) and update both the value and this comment if the workload characteristics
    change materially."""

    # 25MB: ~10x the measured 200-page real-world file, covering large multi-troop schedules
    # with headroom.
    max_upload_bytes: int = 25_000_000
    # 500 pages: 2.5x the 200 pages actually tested successfully end-to-end.
    max_pdf_pages: int = 500
    # 6000px: covers a 400-DPI-rendered US Letter page (measured 3400x4400, so 4400 is the
    # real ceiling at today's highest DPI tier) plus headroom for legal-size paper.
    max_pdf_dimension_px: int = 6_000
    # ~38x the measured 3.125s/200-page baseline -- generous headroom for a slower host or a
    # near-max_pdf_pages file; documented, not force-enforced (see class docstring).
    parse_timeout_seconds: int = 120
    # ~3.75x the measured ~133MB real max RSS for a 200-page file, covering the 500-page
    # ceiling; documented, not force-enforced (see class docstring).
    parse_memory_budget_bytes: int = 500_000_000
