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
from dataclasses import asdict, dataclass, field
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
from scoutmb.core.models import ClassRecord, RequirementRecord  # noqa: F401 - legacy surface
from scoutmb.core.output_schemas import json_for_html  # noqa: F401 - legacy public surface

AJAX_URL = "https://scoutingevent.com/mobile/inc/ajax_mobile.php"
DEAD_ASSET_HOSTS = {
    "mike.dev.admin.247scouting.com",
    "mike.dev.scoutingevent.com",
}


# NOTE: scoutmb.core.models holds the package copies of these four shapes, proven
# field-identical by tests/parity/test_models_parity.py. ClassRecord/RequirementRecord are
# aliases of the package shapes (imported above) as of Slice 2a Task 14; ScoutResult stays
# legacy-defined until Slice 2b, once process_scout stops mutating it.
@dataclass(slots=True)
class ScoutInput:
    name: str
    url: str
    registrant_type: str = ""


@dataclass(slots=True)
class ScoutResult:
    name: str
    qr_url: str
    attendee_id: str = ""
    classes: list[ClassRecord] = field(default_factory=list)
    requirements: list[RequirementRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
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
        default="Scouts Only",
        help='XLSX sheet name (default: "Scouts Only").',
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("scouting-output"),
        help="Output directory (default: scouting-output).",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the Chromium window while running.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Playwright browser channel to use (e.g. 'msedge'); default uses Playwright's bundled Chromium.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Seconds to wait for the schedule response for each scout (default: 45).",
    )
    parser.add_argument(
        "--request-delay-ms",
        type=int,
        default=200,
        help="Delay between class-requirement requests (default: 200 ms).",
    )
    parser.add_argument(
        "--scout-delay-ms",
        type=int,
        default=None,
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
        default="report.html",
        help="HTML report filename inside the output directory (default: report.html).",
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
    return parser.parse_args()


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
    loop = asyncio.get_running_loop()
    future: asyncio.Future[Response] = loop.create_future()

    async def inspect_response(response: Response) -> None:
        if not future.done() and is_schedule_response(response):
            future.set_result(response)

    def on_response(response: Response) -> None:
        asyncio.create_task(inspect_response(response))

    page.on("response", on_response)
    try:
        # Attach the response listener before navigation so an eager page cannot race us.
        await page.goto(qr_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)

        # The schedule sometimes loads automatically after the QR redirect.
        await page.wait_for_timeout(1200)
        if not future.done():
            selectors = [
                'a[href="#scoutPage"]',
                'a[href$="event.html#scoutPage"]',
                'a:has-text("Schedule")',
            ]
            clicked = False
            for selector in selectors:
                locator = page.locator(selector)
                try:
                    if await locator.count():
                        await locator.first.click(force=True, timeout=5000)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                # Invoke the existing handler in-page if the old UI is not considered clickable.
                await page.evaluate(
                    """() => {
                        const link = document.querySelector('a[href="#scoutPage"]') ||
                                     [...document.querySelectorAll('a')].find(a =>
                                         (a.textContent || '').trim().toLowerCase() === 'schedule');
                        if (link) link.click();
                    }"""
                )
        return await asyncio.wait_for(future, timeout=timeout_seconds)
    finally:
        page.remove_listener("response", on_response)


async def post_requirement(page: Page, attendee_id: str, class_p4_id: str) -> dict[str, Any]:
    result = await page.evaluate(
        """async ({url, attendeeId, classP4Id}) => {
            const body = new URLSearchParams({
                getClassRequirement: 'true',
                classP4ID: classP4Id,
                attendeeID: attendeeId,
                TimeStamp: new Date().toString()
            });
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: body.toString()
            });
            return {
                ok: response.ok,
                status: response.status,
                text: await response.text()
            };
        }""",
        {"url": AJAX_URL, "attendeeId": attendee_id, "classP4Id": class_p4_id},
    )
    if not result["ok"]:
        raise RuntimeError(f"Requirement request returned HTTP {result['status']}")
    try:
        return json.loads(result["text"])
    except json.JSONDecodeError as exc:
        preview = result["text"][:300].replace("\n", " ")
        raise RuntimeError(f"Requirement response was not JSON: {preview}") from exc


async def process_scout(
    browser: Browser,
    scout: ScoutInput,
    args: argparse.Namespace,
    raw_dir: Path,
    run_identity: RunIdentity | None = None,
) -> ScoutResult:
    run_identity = run_identity or RunIdentity()
    context: BrowserContext = await browser.new_context(ignore_https_errors=True)

    if not args.allow_dead_assets:
        async def block_dead_assets(route: Any) -> None:
            try:
                hostname = re.sub(r"^https?://", "", route.request.url).split("/", 1)[0].split(":", 1)[0]
                if hostname in DEAD_ASSET_HOSTS:
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                await route.continue_()
        await context.route("**/*", block_dead_assets)

    page = await context.new_page()
    page.set_default_timeout(args.timeout * 1000)
    result = ScoutResult(name=scout.name or "Unknown Scout", qr_url=scout.url)

    page.on("pageerror", lambda error: print(f"    browser JS error: {error}", file=sys.stderr))

    try:
        schedule_response = await navigate_and_trigger_schedule(page, scout.url, args.timeout)
        request_values = form_values(schedule_response.request.post_data)
        attendee_id = request_values.get("attendeeID", "")
        if not attendee_id:
            raise RuntimeError("The schedule request did not contain attendeeID")

        result.attendee_id = attendee_id
        result.name = await discover_name(page, scout.name)

        schedule_payload = await schedule_response.json()
        raw_dir.mkdir(parents=True, exist_ok=True)
        output_id = run_identity.output_id(AttendeeId.parse(attendee_id, result.name))
        slug = attendee_filename_stem(result.name, output_id)
        (raw_dir / f"{slug}-schedule.json").write_text(
            json.dumps(schedule_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if int(schedule_payload.get("status", {}).get("status", 0)) != 1:
            raise RuntimeError(f"Schedule API returned failure: {schedule_payload.get('status')}")

        schedule_rows = schedule_payload.get("data") or []
        deduped_rows: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in schedule_rows:
            key = str(item.get("classP4ID") or "")
            if not key:
                key = f"__no_id_{len(order)}"  # no ID to dedupe on; treat as its own class
                deduped_rows[key] = item
                order.append(key)
            elif key not in deduped_rows:
                deduped_rows[key] = item
                order.append(key)
            elif truthy(item.get("CLASS_COMPLETED")) and not truthy(deduped_rows[key].get("CLASS_COMPLETED")):
                deduped_rows[key] = item  # prefer the completed duplicate — status should not regress
        schedule_rows = [deduped_rows[key] for key in order]

        for item in schedule_rows:
            raw_class_name = str(item.get("CLASS_NAME") or "")
            class_record = ClassRecord(
                scout_name=result.name,
                attendee_id=attendee_id,
                class_number=str(item.get("CLASS_NBR") or ""),
                class_p4_id=str(item.get("classP4ID") or ""),
                class_name=str(item.get("CLASS_NAME_ONLY") or ""),
                days=days_from_class_name(raw_class_name),
                period_name=str(item.get("PERIOD_NAME") or ""),
                start_time=str(item.get("CLASS_STIME") or ""),
                start_time_24h=str(item.get("STIME") or ""),
                location=str(item.get("LOCATION_ROOM_NAME") or ""),
                has_requirements=truthy(item.get("HAS_REQ")),
                class_completed=truthy(item.get("CLASS_COMPLETED")),
                raw_class_name=raw_class_name,
            )
            result.classes.append(class_record)

            if not class_record.class_p4_id:
                continue

            requirement_payload: dict[str, Any] | None = None
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    requirement_payload = await post_requirement(
                        page, attendee_id, class_record.class_p4_id
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    await page.wait_for_timeout(500 * attempt)

            if requirement_payload is None:
                result.errors.append(
                    f"{class_record.class_name}: requirement request failed: {last_error}"
                )
                continue

            (raw_dir / f"{slug}-{safe_slug(class_record.class_number or class_record.class_p4_id)}-requirements.json").write_text(
                json.dumps(requirement_payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            if int(requirement_payload.get("status", {}).get("status", 0)) != 1:
                result.errors.append(
                    f"{class_record.class_name}: requirement API returned failure: "
                    f"{requirement_payload.get('status')}"
                )
                continue

            for req in requirement_payload.get("data") or []:
                result.requirements.append(
                    RequirementRecord(
                        scout_name=result.name,
                        attendee_id=attendee_id,
                        class_number=class_record.class_number,
                        class_p4_id=class_record.class_p4_id,
                        merit_badge_name=str(req.get("MERIT_BADGE_NAME") or ""),
                        requirement_id=str(req.get("MDM_LKP_BADGE_REQ_ID") or ""),
                        requirement_type_id=str(req.get("MDM_LKP_BADGE_REQ_TYPE_ID") or ""),
                        requirement_number=str(req.get("REQ_NBR_WEB_DISPLAY") or req.get("REQ_NBR") or ""),
                        description=clean_html_description(str(req.get("REQ_DESCR") or "")),
                        completed_requirement=truthy(req.get("COMPLETED_REQ_FLAG")),
                        completed_class=truthy(req.get("COMPLETED_CLASS_FLAG")),
                        requirement_on_event=truthy(req.get("REQ_ON_EVENT")),
                        present_days=str(req.get("PRESENT_DAYS") or "").strip(),
                    )
                )

            if args.request_delay_ms > 0:
                await page.wait_for_timeout(args.request_delay_ms)

    except Exception as exc:
        result.errors.append(str(exc))
    finally:
        await context.close()

    return result


def _attendee_key_for(item: dict[str, Any]) -> str:
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
        results,
        generated_at_local=generated_at_local,
        generated_at_iso=generated_at_iso,
        run_identity=run_identity,
        generate_html=generate_html,
        html_name=html_name,
        generate_email_report=generate_email_report,
    )


async def async_main(
    args: argparse.Namespace,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    scouts = load_inputs(args.input, args.sheet, args.include_adults)
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output / "raw"

    print(f"Loaded {len(scouts)} attendee QR link(s).")
    if progress_callback is not None:
        await progress_callback({"type": "batch_start", "total": len(scouts)})
    results: list[ScoutResult] = []

    run_identity = RunIdentity()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not args.headed, channel=getattr(args, "channel", None) or None
        )
        try:
            for index, scout in enumerate(scouts, start=1):
                if resume_event is not None and not resume_event.is_set():
                    if progress_callback is not None:
                        await progress_callback({"type": "paused", "index": index, "total": len(scouts)})
                    await resume_event.wait()
                    if progress_callback is not None:
                        await progress_callback({"type": "resumed", "index": index, "total": len(scouts)})

                label = scout.name or scout.url
                print(f"[{index}/{len(scouts)}] {label}")
                if progress_callback is not None:
                    await progress_callback(
                        {"type": "scout_start", "index": index, "total": len(scouts), "name": label}
                    )
                result = await process_scout(browser, scout, args, raw_dir, run_identity)
                results.append(result)
                print(
                    f"    attendeeID={result.attendee_id or 'unknown'}, "
                    f"classes={len(result.classes)}, requirements={len(result.requirements)}, "
                    f"errors={len(result.errors)}"
                )
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "type": "scout_done",
                            "index": index,
                            "total": len(scouts),
                            "name": label,
                            "attendee_id": result.attendee_id,
                            "classes": len(result.classes),
                            "requirements": len(result.requirements),
                            "errors": len(result.errors),
                        }
                    )
                if index < len(scouts):
                    delay_seconds = (
                        random.uniform(0.5, 2.0)
                        if args.scout_delay_ms is None
                        else args.scout_delay_ms / 1000
                    )
                    if delay_seconds > 0:
                        await asyncio.sleep(delay_seconds)
        finally:
            await browser.close()

    write_outputs(
        args.output,
        results,
        generate_html=not args.no_html,
        html_name=args.html_name,
        generate_email_report=getattr(args, "email_report", False),
        run_identity=run_identity,
    )
    print(f"Results written to: {args.output.resolve()}")
    return 1 if any(result.errors for result in results) else 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
