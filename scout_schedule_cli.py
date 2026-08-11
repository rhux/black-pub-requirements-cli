#!/usr/bin/env python3
"""Download Scout schedules and class requirements from scoutingevent.com QR links.

The site currently returns the data successfully but its old jQuery Mobile renderer can
fail before the schedule list is initialized. This CLI uses a real browser only to
establish the PHP session and trigger the schedule request, then reads the JSON payloads
directly.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs

# NOTE: this import must stay BEFORE the playwright import below. The frozen
# IN-IMPORT-003 catalog case (tests/matrix/cases/input_cases.py) observes which
# modules are in sys.modules when playwright's ImportError fires under the
# acquisition profile -- openpyxl needs to already be imported by then.
# Reordering this will silently change that case's expected output.
# (IN-IMPORT-004's all profile blocks openpyxl too, so it fails on its own
# import before order/placement matters -- unaffected by this note.)
from scoutmb.adapters.files.tabular import (  # noqa: F401 - legacy public surface
    first_matching_key,
    load_csv,
    load_json,
    load_text,
    load_xlsx,
    norm_header,
)

from playwright.async_api import Browser, Page, Response

from scoutmb.adapters.files.atomic import atomic_write_text, write_csv  # noqa: F401
from scoutmb.core.identity import (  # noqa: F401 - re-exported for the legacy public surface
    AttendeeId,
    MissingAttendeeId,
    RunIdentity,
    attendee_filename_stem,
    safe_slug,
)
from scoutmb.core.inference.numbering import (  # noqa: F401 - legacy public surface
    CHOICE_COUNT_WORDS,
    choice_requirement_count,
    requirement_path,
)
from scoutmb.core.models import (  # noqa: F401 - legacy surface
    ClassRecord,
    RequirementRecord,
    ScoutInput,
)
from scoutmb.core.output_schemas import json_for_html  # noqa: F401 - legacy public surface

AJAX_URL = "https://scoutingevent.com/mobile/inc/ajax_mobile.php"
DEAD_ASSET_HOSTS = {
    "mike.dev.admin.247scouting.com",
    "mike.dev.scoutingevent.com",
}


# NOTE: scoutmb.core.models holds the package copies of these four shapes, proven
# field-identical by tests/parity/test_models_parity.py. ClassRecord/RequirementRecord/
from scoutmb.core.models import ScoutResult  # noqa: F401 - legacy public surface


from scoutmb.config import ScheduleConfig
from scoutmb.interfaces.cli.schedule import main  # noqa: F401 - legacy public surface

# Sourced once, here: every non-required argparse default below reads this instance rather than
# repeating a literal, so ScheduleConfig's own field defaults are the single source of truth
# tests/contracts/test_cli_defaults_parity.py checks against.
_DEFAULTS = ScheduleConfig(input=Path("unused"))


def parse_args() -> ScheduleConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Pull schedules and class requirements from ScoutingEvent QR URLs, "
            "bypassing the site's broken jQuery Mobile rendering."
        )
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="CSV, XLSX, JSON, or text file containing scout names and QR URLs.",
    )
    parser.add_argument(
        "--sheet",
        default=_DEFAULTS.sheet,
        help=f'XLSX sheet name (default: "{_DEFAULTS.sheet}").',
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=_DEFAULTS.output,
        help=f"Output directory (default: {_DEFAULTS.output}).",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the Chromium window while running.",
    )
    parser.add_argument(
        "--channel",
        default=_DEFAULTS.channel,
        help="Playwright browser channel to use (e.g. 'msedge'); default uses Playwright's bundled Chromium.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULTS.timeout,
        help=f"Seconds to wait for the schedule response for each scout (default: {_DEFAULTS.timeout}).",
    )
    parser.add_argument(
        "--request-delay-ms",
        type=int,
        default=_DEFAULTS.request_delay_ms,
        help=f"Delay between class-requirement requests (default: {_DEFAULTS.request_delay_ms} ms).",
    )
    parser.add_argument(
        "--scout-delay-ms",
        type=int,
        default=_DEFAULTS.scout_delay_ms,
        help=(
            "Delay between scouts, in milliseconds. Default: a random delay "
            "between 500-2000 ms per scout (so requests don't hit the server at a "
            "fixed cadence); pass a fixed value (e.g. 0 to disable, or 750 for a "
            "fixed 750ms) to override."
        ),
    )
    parser.add_argument(
        "--allow-dead-assets",
        action="store_true",
        help="Do not block the two known mike.dev.* JavaScript URLs that currently time out.",
    )
    parser.add_argument(
        "--include-adults",
        action="store_true",
        help="Include Adult and Part-Time Adult rows when the input contains a Registrant Type column.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Do not generate the self-contained sortable/filterable HTML report.",
    )
    parser.add_argument(
        "--html-name",
        default=_DEFAULTS.html_name,
        help=f"HTML report filename inside the output directory (default: {_DEFAULTS.html_name}).",
    )
    parser.add_argument(
        "--email-report",
        action="store_true",
        help=(
            "Also generate per-scout missing-requirement emails (HTML, text, and a "
            "combined CSV) in an 'emails' subdirectory of the output directory. "
            "The HTML report's 'Generate missing-requirement emails' button does "
            "this on demand when run through the local web UI, so this flag is "
            "only needed for bare command-line runs (default: off)."
        ),
    )
    parser.add_argument(
        "--breaker-threshold",
        type=int,
        default=_DEFAULTS.breaker_threshold,
        help=(
            "Consecutive scout-fetch failures before the acquisition circuit breaker opens "
            f"and the batch stops (default: {_DEFAULTS.breaker_threshold})."
        ),
    )
    args = parser.parse_args()
    return ScheduleConfig(
        input=args.input,
        sheet=args.sheet,
        output=args.output,
        headed=args.headed,
        channel=args.channel,
        timeout=args.timeout,
        request_delay_ms=args.request_delay_ms,
        scout_delay_ms=args.scout_delay_ms,
        allow_dead_assets=args.allow_dead_assets,
        include_adults=args.include_adults,
        no_html=args.no_html,
        html_name=args.html_name,
        email_report=args.email_report,
        breaker_threshold=args.breaker_threshold,
    )


def load_inputs(path: Path, sheet_name: str, include_adults: bool) -> list[ScoutInput]:
    from scoutmb.adapters.files.tabular import TabularAttendeeSource
    from scoutmb.features.ingest.service import IngestService

    service = IngestService(
        sources=(TabularAttendeeSource(sheet_name=sheet_name),), include_adults=include_adults
    )
    return service.load(path)


def form_values(post_data: str | None) -> dict[str, str]:
    parsed = parse_qs(post_data or "", keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


async def navigate_and_trigger_schedule(page: Page, qr_url: str, timeout_seconds: int) -> Response:
    from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway

    return await PlaywrightScoutingEventGateway._fetch_schedule_on_page(page, qr_url, timeout_seconds)


async def post_requirement(page: Page, attendee_id: str, class_p4_id: str) -> dict[str, Any]:
    from scoutmb.adapters.scoutevent.http_gateway import fetch_requirement_payload

    return await fetch_requirement_payload(page, attendee_id, class_p4_id)


async def process_scout(
    browser: Browser,
    scout: ScoutInput,
    config: ScheduleConfig,
    raw_dir: Path,
    run_identity: RunIdentity | None = None,
) -> ScoutResult:
    from scoutmb.adapters.files.atomic import AtomicFileSink
    from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
    from scoutmb.features.acquisition.retry import RetryPolicy
    from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
    from scoutmb.ports.clock import MonotonicSleeper, SeededJitter

    run_identity = run_identity or RunIdentity()
    gateway = PlaywrightScoutingEventGateway(browser, allow_dead_assets=config.allow_dead_assets)
    retry_policy = RetryPolicy(
        sleeper=MonotonicSleeper(), jitter=SeededJitter(), breaker_threshold=config.breaker_threshold
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    return await service.process(
        scout=scout,
        config=AcquisitionConfig(
            timeout_seconds=config.timeout, request_delay_ms=config.request_delay_ms
        ),
        raw_dir=raw_dir,
        run_identity=run_identity,
    )


def write_outputs(
    output_dir: Path,
    results: list[ScoutResult],
    *,
    generate_html: bool = True,
    html_name: str = "report.html",
    generate_email_report: bool = False,
    run_identity: RunIdentity | None = None,
) -> None:
    """Form-2 shim: compute the two wall-clock timestamps, then delegate the actual record
    composition and file writes to ReportingService.publish (features/reporting/service.py),
    built through the composition root."""
    # One identity per run. A fresh instance here would mint UUIDs unrelated to the ones the
    # rest of the run already used for this attendee's raw/ files.
    run_identity = run_identity or RunIdentity()
    generated_at_local = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    generated_at_iso = datetime.now().astimezone().isoformat(timespec="seconds")

    from scoutmb.interfaces.cli.composition import build_reporting_service

    build_reporting_service().publish(
        output_dir,
        results,  # type: ignore[arg-type]  # ScoutResult twin types are duck-type
        # compatible; real alias deferred to Slice 2b (see class ScoutResult comment above)
        generated_at_local=generated_at_local,
        generated_at_iso=generated_at_iso,
        run_identity=run_identity,
        generate_html=generate_html,
        html_name=html_name,
        generate_email_report=generate_email_report,
    )


async def async_main(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    from scoutmb.interfaces.cli.schedule import run

    return await run(config, progress_callback=progress_callback, resume_event=resume_event)


if __name__ == "__main__":
    raise SystemExit(main())
