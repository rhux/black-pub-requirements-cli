"""troop349-schedule console script: argument-for-argument identical to scout_schedule_cli.py's
CLI. Interface layer -- argument parsing and orchestration only, mirroring interfaces/cli/pdf.py's
existing shape. This module no longer imports scout_schedule_cli at all (B10.2), so Task B10.4's
deletion of that file cannot break it. The argparse construction is a duplicate of
scout_schedule_cli.parse_args's (both read their defaults from ScheduleConfig, sub-plan 2's Task
B6, so the two cannot silently drift on default VALUES -- only the flag/help text structure is
duplicated here, matching this codebase's existing precedent for a flat-script/package shim
boundary, e.g. features/reporting/service.py's own module docstring: "duplicate
scout_schedule_cli.py's same-named functions rather than importing them... kept in lockstep by
inspection.")

run() is the ONE place that composes the schedule CLI's adapters (via composition.py's builders)
and calls run_schedule_pipeline -- both this module's own main() and scout_schedule_cli.async_main's
shim call run(), so the composition logic exists exactly once."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from scoutmb.config import ScheduleConfig, UiSettings
from scoutmb.logging_setup import configure_logging

_DEFAULTS = ScheduleConfig(input=Path("unused"))


def parse_args(argv: list[str] | None = None) -> ScheduleConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Pull schedules and class requirements from ScoutingEvent QR URLs, "
            "bypassing the site's broken jQuery Mobile rendering."
        )
    )
    parser.add_argument("--input", "-i", required=True, type=Path, help=(
        "CSV, XLSX, JSON, or text file containing scout names and QR URLs."
    ))
    parser.add_argument("--sheet", default=_DEFAULTS.sheet, help=(
        f'XLSX sheet name (default: "{_DEFAULTS.sheet}").'
    ))
    parser.add_argument("--output", "-o", type=Path, default=_DEFAULTS.output, help=(
        f"Output directory (default: {_DEFAULTS.output})."
    ))
    parser.add_argument("--headed", action="store_true", help="Show the Chromium window while running.")
    parser.add_argument("--channel", default=_DEFAULTS.channel, help=(
        "Playwright browser channel to use (e.g. 'msedge'); default uses Playwright's bundled Chromium."
    ))
    parser.add_argument("--timeout", type=int, default=_DEFAULTS.timeout, help=(
        f"Seconds to wait for the schedule response for each scout (default: {_DEFAULTS.timeout})."
    ))
    parser.add_argument("--request-delay-ms", type=int, default=_DEFAULTS.request_delay_ms, help=(
        f"Delay between class-requirement requests (default: {_DEFAULTS.request_delay_ms} ms)."
    ))
    parser.add_argument("--scout-delay-ms", type=int, default=_DEFAULTS.scout_delay_ms, help=(
        "Delay between scouts, in milliseconds. Default: a random delay "
        "between 500-2000 ms per scout (so requests don't hit the server at a "
        "fixed cadence); pass a fixed value (e.g. 0 to disable, or 750 for a "
        "fixed 750ms) to override."
    ))
    parser.add_argument("--allow-dead-assets", action="store_true", help=(
        "Do not block the two known mike.dev.* JavaScript URLs that currently time out."
    ))
    parser.add_argument("--include-adults", action="store_true", help=(
        "Include Adult and Part-Time Adult rows when the input contains a Registrant Type column."
    ))
    parser.add_argument("--no-html", action="store_true", help=(
        "Do not generate the self-contained sortable/filterable HTML report."
    ))
    parser.add_argument("--html-name", default=_DEFAULTS.html_name, help=(
        f"HTML report filename inside the output directory (default: {_DEFAULTS.html_name})."
    ))
    parser.add_argument("--email-report", action="store_true", help=(
        "Also generate per-scout missing-requirement emails (HTML, text, and a "
        "combined CSV) in an 'emails' subdirectory of the output directory."
    ))
    parser.add_argument("--breaker-threshold", type=int, default=_DEFAULTS.breaker_threshold, help=(
        "Consecutive scout-fetch failures before the acquisition circuit breaker opens and "
        f"the batch stops (default: {_DEFAULTS.breaker_threshold})."
    ))
    args = parser.parse_args(argv)
    return ScheduleConfig(
        input=args.input, sheet=args.sheet, output=args.output, headed=args.headed,
        channel=args.channel, timeout=args.timeout, request_delay_ms=args.request_delay_ms,
        scout_delay_ms=args.scout_delay_ms, allow_dead_assets=args.allow_dead_assets,
        include_adults=args.include_adults, no_html=args.no_html, html_name=args.html_name,
        email_report=args.email_report, breaker_threshold=args.breaker_threshold,
    )


async def run(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    """Composes the schedule CLI's adapters and calls run_schedule_pipeline. The ONE place that
    does this composition -- main() below and scout_schedule_cli.async_main's shim both call
    this rather than each building their own gateway/checkpoint-store/browser."""
    from scoutmb.features.acquisition.pipeline import run_schedule_pipeline
    from scoutmb.features.acquisition.retry import RetryPolicy
    from scoutmb.interfaces.cli.composition import (
        build_acquisition_service,
        build_checkpoint_store,
        build_ingest_service,
        build_launched_browser,
        build_reporting_service,
        build_schedule_gateway,
    )
    from scoutmb.ports.clock import MonotonicSleeper, SeededJitter

    scouts = build_ingest_service(
        sheet_name=config.sheet, include_adults=config.include_adults
    ).load(config.input)
    checkpoint_store = build_checkpoint_store(config.output / "checkpoint.json")
    # ONE RetryPolicy, shared between the AcquisitionService (per-request backoff) and
    # run_schedule_pipeline/run_batch (the cross-scout breaker) -- see pipeline.py's own
    # docstring on why this sharing is this caller's contract to uphold.
    retry_policy = RetryPolicy(
        sleeper=MonotonicSleeper(), jitter=SeededJitter(), breaker_threshold=config.breaker_threshold
    )

    async with build_launched_browser(headed=config.headed, channel=config.channel) as browser:
        gateway = build_schedule_gateway(browser, allow_dead_assets=config.allow_dead_assets)
        service = build_acquisition_service(gateway, retry_policy)
        return await run_schedule_pipeline(
            config,
            scouts=scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=build_reporting_service(),
            progress_callback=progress_callback,
            resume_event=resume_event,
        )


def main() -> int:
    config = parse_args()
    configure_logging(UiSettings.resolve().data_root)
    try:
        return asyncio.run(run(config))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
