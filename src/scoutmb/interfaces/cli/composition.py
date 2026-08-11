"""The ONLY module under interfaces/cli permitted to import an adapter.

Named by convention so the architecture test can enforce it: "a module whose sole job is
wiring" is not a property a linter can evaluate, so the filename carries the rule
(tests/architecture's test_adapter_imports_confined_to_composition_roots).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.files.tabular import TabularAttendeeSource
from scoutmb.adapters.html.report import render_report
from scoutmb.adapters.pdf.pages import extract_pdf as _extract_pdf
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.models import ExtractedAttendee, ExtractionError
from scoutmb.errors import CapabilityUnavailable
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionService
from scoutmb.features.ingest.service import IngestService
from scoutmb.features.reporting.service import ReportingService
from scoutmb.ports.checkpoint_store import CheckpointStore
from scoutmb.ports.scoutevent import ScoutingEventGateway

if TYPE_CHECKING:
    from playwright.async_api import Browser


def build_ingest_service(
    *, sheet_name: str = "Scouts Only", include_adults: bool = False
) -> IngestService:
    return IngestService(
        sources=(TabularAttendeeSource(sheet_name=sheet_name),), include_adults=include_adults
    )


def build_reporting_service() -> ReportingService:
    return ReportingService(sink=AtomicFileSink(), renderer=render_report)


class PdfExtractor(Protocol):
    """The callable shape interfaces/cli/pdf.py needs from the PDF extraction adapter.

    A plain ``Callable[[...], ...]`` type erases parameter names, so mypy rejects main()'s
    keyword call (``extract_pdf(pdf_path=..., dpis=..., ...)``) against it -- this Protocol's
    ``__call__`` keeps the names so the keyword call type-checks against the real
    ``adapters.pdf.pages.extract_pdf`` it is structurally satisfied by.
    """

    def __call__(
        self,
        pdf_path: Path,
        dpis: Sequence[int],
        normalize_case: bool,
        debug_dir: Path | None,
    ) -> tuple[list[ExtractedAttendee], list[ExtractionError]]: ...


def build_pdf_extractor() -> PdfExtractor:
    """Return the PDF page-extraction function, wired to the real fitz/cv2 adapter.

    interfaces/cli/pdf.py obtains its extractor through here rather than importing
    scoutmb.adapters.pdf.pages directly, keeping every adapter import in this file.
    """
    return _extract_pdf


# Playwright itself is imported function-local inside build_launched_browser, not at this
# module's top level: the "acquisition" extra (pyproject.toml) is optional, and every OTHER
# builder already in this file (build_ingest_service, build_reporting_service,
# build_pdf_extractor) must keep working without it installed -- a module-scope playwright
# import would break composition.py entirely for a PDF-only install. This is the ONLY place in
# the package that calls async_playwright() itself.
@asynccontextmanager
async def build_launched_browser(
    *, headed: bool, channel: str | None
) -> AsyncIterator[Browser]:
    """Launches ONE Chromium browser for a schedule-CLI run and guarantees it is closed even on
    an exception -- interfaces/cli/schedule.py's run() holds this open for the whole batch, the
    same lifetime scout_schedule_cli.async_main's inline `async with async_playwright()` block
    used to have."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise CapabilityUnavailable(
            capability="acquisition", distributions=("playwright",), extra="acquisition"
        ) from exc

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed, channel=channel)
        try:
            yield browser
        finally:
            await browser.close()


def build_schedule_gateway(browser: Browser, *, allow_dead_assets: bool) -> ScoutingEventGateway:
    return PlaywrightScoutingEventGateway(browser, allow_dead_assets=allow_dead_assets)


def build_checkpoint_store(path: Path) -> CheckpointStore:
    return AtomicFileCheckpointStore(path)


def build_acquisition_service(
    gateway: ScoutingEventGateway, retry_policy: RetryPolicy
) -> AcquisitionService:
    return AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
