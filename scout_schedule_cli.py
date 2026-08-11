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
import csv
import html
import io
import json
import random
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
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

from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright

from scoutmb.adapters.files.atomic import atomic_write_text, write_csv  # noqa: F401
from scoutmb.adapters.html.report import render_report
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
from scoutmb.core.inference.missing import group_missing_requirements
from scoutmb.core.inference.status import calculate_statuses
from scoutmb.core.inference.tree import build_group_tree
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


def is_schedule_response(response: Response) -> bool:
    if "ajax_mobile.php" not in response.url:
        return False
    values = form_values(response.request.post_data)
    return values.get("getUnitClass", "").lower() == "true"


def clean_html_description(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def days_from_class_name(class_name: str) -> str:
    if " - " in class_name:
        return class_name.split(" - ", 1)[0].strip()
    return ""


async def discover_name(page: Page, fallback: str) -> str:
    if fallback:
        return fallback
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count():
                text = (await locator.first.inner_text()).strip()
                if text and text.lower() not in {"schedule", "event", "menu"}:
                    return text
        except Exception:
            pass
    return "Unknown Scout"


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


def _assert_blank_identity_results_have_no_records(results: Sequence[ScoutResult]) -> None:
    """Fail loudly if a blank-identity ScoutResult carries class/requirement data.

    Legacy-copy sibling of scoutmb.features.reporting.service._assert_blank_identity_has_no_
    records, kept in lockstep by inspection per this module's docstring. `_attendee_key_for`'s
    `f"name:{scout_name}"` fallback is only safe because process_scout always sets attendee_id
    BEFORE populating classes/requirements (a ScoutResult that failed before identity
    resolution is assumed to always have empty collections). If that invariant were ever
    violated, two different same-named attendees with blank identity would silently merge
    into one inferred requirement structure in report.html, with no exception and no warning.
    Called by write_html_report, which -- unlike write_outputs -- does not route through
    ReportingService.publish and so does not inherit its guard.
    """
    for result in results:
        if str(result.attendee_id or "").strip():
            continue
        if result.classes or result.requirements:
            raise AssertionError(
                f"ScoutResult for {result.name!r} has a blank attendee_id but "
                f"{len(result.classes)} class record(s) and {len(result.requirements)} "
                "requirement record(s). _attendee_key_for's name-based fallback would group "
                "this with any other blank-identity attendee sharing the same name, silently "
                "merging their data -- refusing to write the report instead."
            )


def _assert_blank_identity_scouts_have_no_records(scouts: list[dict[str, Any]]) -> None:
    """Fail loudly if a blank-identity scout dict carries class/requirement data.

    Dict-shape sibling of `_assert_blank_identity_results_have_no_records`, for the nested
    `scouts.json` shape (`{name, attendee_id, classes, requirements, errors}`) that
    build_missing_requirements/write_email_reports consume. This is the guard that actually
    closes the live gap: ui/server.py's `POST /api/runs/{run_id}/generate-emails` calls
    write_email_reports directly with scouts loaded straight off disk from a prior run's
    scouts.json (possibly written by pre-fix code, or hand-edited), never going through
    ReportingService.publish and so never hitting its guard. Without this check,
    `_attendee_key_for`'s name-based fallback would silently merge two same-named
    blank-identity scouts' requirement data with no exception and no warning.
    """
    for scout in scouts:
        attendee_id = str(scout.get("attendee_id") or "").strip()
        if attendee_id:
            continue
        classes = scout.get("classes") or []
        requirements = scout.get("requirements") or []
        if classes or requirements:
            raise AssertionError(
                f"Scout {scout.get('name')!r} has a blank attendee_id but "
                f"{len(classes)} class record(s) and {len(requirements)} requirement "
                "record(s). _attendee_key_for's name-based fallback would group this with any "
                "other blank-identity scout sharing the same name, silently merging their "
                "data -- refusing to build missing-requirement groupings instead."
            )


def _attendee_key_for(item: Mapping[str, Any]) -> str:
    """Grouping identity: the attendee ID, never the display name. Two attendees can
    share a name; merging them silently corrupts both.

    A blank attendee_id cannot occur through the production path (process_scout fails a
    scout closed at :482 when the schedule request has no attendeeID), so the blank branch
    is defensive only. It keys on scout_name — which does not fragment a single scout across
    its requirements the way requirement_id would, and does not depend on id(item), which is
    unstable across the dict copies this function makes.
    """
    attendee_id = str(item.get("attendee_id") or "").strip()
    if attendee_id:
        return attendee_id
    return f"name:{str(item.get('scout_name') or '')}"


def annotate_requirement_statuses(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add inferred display status fields used only by the HTML report.

    The API frequently leaves parent rows incomplete even when every child row is
    complete. Parent status is therefore calculated recursively. Choice parents
    such as 'Do ONE of the following' are marked as completed-but-review when the
    minimum number of alternatives appears complete.
    """
    annotated = [dict(item) for item in requirements]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in annotated:
        grouped.setdefault((_attendee_key_for(item), str(item.get("class_p4_id") or "")), []).append(item)

    for group in grouped.values():
        tree = build_group_tree(
            tuple(str(item.get("requirement_number") or "") for item in group),
            tuple(str(item.get("requirement_type_id") or "") for item in group),
        )
        for item, path in zip(group, tree.paths, strict=True):
            item["requirement_path"] = list(path)
        for index, parent_index in enumerate(tree.parent_index):
            if parent_index is not None:
                group[index]["parent_requirement_number"] = group[parent_index].get(
                    "requirement_number"
                )

        statuses = calculate_statuses(
            tree=tree,
            completed=tuple(bool(item.get("completed_requirement")) for item in group),
            descriptions=tuple(str(item.get("description") or "") for item in group),
        )
        for item, row_status in zip(group, statuses, strict=True):
            item["calculated_status"] = row_status.status
            item["calculated_status_reason"] = row_status.reason
            # Presence, not value: is_actionable_leaf gates on `"total_subrequirements" not in item`.
            if row_status.total_subrequirements is not None:
                item["completed_subrequirements"] = row_status.completed_subrequirements
                item["total_subrequirements"] = row_status.total_subrequirements
                item["choice_required_count"] = row_status.choice_required_count

    return annotated


def build_missing_requirements(scouts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group incomplete, actionable requirements by scout name and merit badge.

    `scouts` is the same nested shape written to scouts.json: a list of
    {name, attendee_id, classes, requirements, errors} dicts. Leaf requirements
    (no children) left 'incomplete' by annotate_requirement_statuses are the
    actionable items; section headers and parent rollups aren't actionable on
    their own, but when a leaf is missing, its still-incomplete ancestors (e.g.
    "3" when "3b"/"3c" are missing) are included too for context -- a scout
    seeing "3b" in isolation has no idea what "3" actually asked for.
    """
    _assert_blank_identity_scouts_have_no_records(scouts)
    flattened = [dict(req) for scout in scouts for req in scout.get("requirements", [])]
    annotated = annotate_requirement_statuses(flattened)
    return group_missing_requirements(
        annotated,
        attendee_key_of=_attendee_key_for,
        clean_description=clean_html_description,
    )


def email_subject(scout_name: str) -> str:
    return f"Merit Badge Requirements Still Needed - {scout_name}"


def render_email_text(scout_name: str, badge_groups: dict[str, list[dict[str, Any]]]) -> str:
    lines = [f"Hi {scout_name},", "", "Here are the merit badge requirements you still need to complete:"]
    for badge_name, items in badge_groups.items():
        lines.append("")
        lines.append(badge_name)
        lines.append("-" * len(badge_name))
        for item in items:
            indent = "  " * (item["depth"] + 1)
            prefix = f"{indent}{item['requirement_number']}. " if item["requirement_number"] else indent
            body = item["description"].replace("\n", "\n" + " " * len(prefix))
            line = f"{prefix}{body}"
            if item["is_prereq"]:
                line += " (complete before the event)"
            lines.append(line)
    lines.append("")
    lines.append("Please work with your merit badge counselor to complete these. Reach out if you have questions.")
    return "\n".join(lines)


def render_email_html(scout_name: str, badge_groups: dict[str, list[dict[str, Any]]]) -> str:
    sections = []
    for badge_name, items in badge_groups.items():
        rows = []
        for item in items:
            number = html.escape(item["requirement_number"])
            description = html.escape(item["description"]).replace("\n", "<br>")
            prereq_badge = (
                ' <span class="prereq">complete before the event</span>' if item["is_prereq"] else ""
            )
            indent = f' style="margin-left: {item["depth"] * 1.25}rem"' if item["depth"] else ""
            rows.append(f"<li{indent}><strong>{number}.</strong> {description}{prereq_badge}</li>")
        sections.append(f"<h2>{html.escape(badge_name)}</h2><ul>{''.join(rows)}</ul>")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Merit Badge Requirements Still Needed - {html.escape(scout_name)}</title>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; color: #17212b; max-width: 640px; margin: 0 auto; padding: 1.5rem; line-height: 1.5; }}
h1 {{ font-size: 1.4rem; }}
h2 {{ font-size: 1.1rem; margin-top: 1.5rem; border-bottom: 2px solid #245b78; padding-bottom: .25rem; }}
ul {{ padding-left: 1.25rem; }}
li {{ margin-bottom: .5rem; }}
.prereq {{ display: inline-block; font-size: .75rem; font-weight: bold; color: #8a4b08; background: #fff0d8; border-radius: 4px; padding: .05rem .4rem; }}
</style>
</head>
<body>
<h1>Hi {html.escape(scout_name)},</h1>
<p>Here are the merit badge requirements you still need to complete:</p>
{"".join(sections)}
<p>Please work with your merit badge counselor to complete these. Reach out if you have questions.</p>
</body>
</html>
"""


def write_email_reports(
    output_dir: Path,
    scouts: list[dict[str, Any]],
    *,
    run_identity: RunIdentity | None = None,
) -> Path:
    """Write per-scout missing-requirement emails plus a combined mail-merge CSV."""
    emails_dir = output_dir / "emails"
    emails_dir.mkdir(parents=True, exist_ok=True)
    missing = build_missing_requirements(scouts)
    # One identity per run. A fresh instance here would mint UUIDs unrelated to the ones the
    # rest of the run already used for this attendee's raw/ files.
    run_identity = run_identity or RunIdentity()

    fieldnames = [
        "scout_name", "attendee_id", "status", "merit_badge_count",
        "missing_requirement_count", "subject", "body_text", "body_html",
    ]
    csv_rows = []
    for scout in scouts:
        scout_name = str(scout.get("name") or "")
        attendee_id = str(scout.get("attendee_id") or "")
        attendee_key = attendee_id.strip() or f"unresolved-{scout_name}"
        bucket = missing.get(attendee_key) or {"display_name": scout_name, "badges": {}}
        badge_groups = bucket["badges"]
        missing_count = sum(1 for items in badge_groups.values() for item in items if item["is_leaf"])

        if missing_count:
            status = "missing_requirements"
        elif not scout.get("requirements") and scout.get("errors"):
            status = "no_data_scraped"
        else:
            status = "all_complete"

        subject = email_subject(scout_name)
        body_text = render_email_text(scout_name, badge_groups) if missing_count else ""
        body_html = render_email_html(scout_name, badge_groups) if missing_count else ""

        if missing_count:
            output_id = run_identity.output_id(AttendeeId.parse(attendee_id, scout_name))
            slug = attendee_filename_stem(scout_name, output_id)
            atomic_write_text(emails_dir / f"{slug}.txt", body_text, encoding="utf-8")
            atomic_write_text(emails_dir / f"{slug}.html", body_html, encoding="utf-8")

        csv_rows.append(
            {
                "scout_name": scout_name,
                "attendee_id": attendee_id,
                "status": status,
                "merit_badge_count": len(badge_groups),
                "missing_requirement_count": missing_count,
                "subject": subject,
                "body_text": body_text,
                "body_html": body_html,
            }
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(csv_rows)
    atomic_write_text(emails_dir / "missing_requirements.csv", buffer.getvalue())

    return emails_dir


def write_html_report(
    path: Path,
    results: list[ScoutResult],
    generated_at_local: str,
    generated_at_iso: str,
    run_id: str = "",
) -> None:
    """DEAD in production as of Slice 2a Task 22: `write_outputs` no longer calls this,
    routing report.html through `ReportingService.publish` instead (see that class's module
    docstring). This copy is kept alive only because the frozen ART-*/REQ-B-* characterization
    catalog still calls it directly.

    Do NOT call this from new code and do NOT copy it as a template for a new HTML-writing
    path: unlike `ReportingService`, this embeds `scouts[i]["attendee_id"]` verbatim below,
    never substituting the shareable `output_id` -- the exact PII this slice exists to keep out
    of report.html. It has already silently diverged from the live path on this one property;
    nothing catches a further divergence except a human reading both copies side by side.
    """
    _assert_blank_identity_results_have_no_records(results)
    classes = [asdict(item) for result in results for item in result.classes]
    requirements = annotate_requirement_statuses(
        [asdict(item) for result in results for item in result.requirements]
    )
    errors = [
        {"scout_name": result.name, "attendee_id": result.attendee_id, "error": error}
        for result in results
        for error in result.errors
    ]
    scouts = [
        {
            "name": result.name,
            "attendee_id": result.attendee_id,
            "class_count": len(result.classes),
            "requirement_count": len(result.requirements),
            "error_count": len(result.errors),
        }
        for result in results
    ]
    report_data = {
        "generated_at_local": generated_at_local,
        "generated_at_iso": generated_at_iso,
        "run_id": run_id,
        "scouts": scouts,
        "classes": classes,
        "requirements": requirements,
        "errors": errors,
    }

    atomic_write_text(path, render_report(report_data), encoding="utf-8")


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
    built through the composition root. write_html_report/write_email_reports and their
    helpers stay defined below, unchanged and still directly tested -- ReportingService owns
    its own equivalent logic since it (a package module) cannot import back from this script.
    """
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
