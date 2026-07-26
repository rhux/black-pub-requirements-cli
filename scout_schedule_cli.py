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
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs

from scoutmb.adapters.files.tabular import (  # noqa: F401 - legacy public surface
    first_matching_key,
    load_csv,
    load_json,
    load_text,
    load_xlsx,
    norm_header,
)

from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright

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
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        scouts = load_xlsx(path, sheet_name)
    elif suffix == ".csv":
        scouts = load_csv(path)
    elif suffix == ".json":
        scouts = load_json(path)
    else:
        scouts = load_text(path)

    filtered: list[ScoutInput] = []
    seen: set[str] = set()
    for scout in scouts:
        scout.url = scout.url.strip()
        scout.name = scout.name.strip()
        scout.registrant_type = scout.registrant_type.strip()
        if not scout.url.startswith("https://scoutingevent.com/mobile/"):
            continue
        if not include_adults and scout.registrant_type.lower() in {"adult", "part-time adult"}:
            continue
        if scout.url in seen:
            continue
        seen.add(scout.url)
        filtered.append(scout)

    if not filtered:
        raise ValueError(f"No ScoutingEvent QR URLs found in {path}")
    return filtered


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


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Render-first, same-dir temp, fsync, atomic replace. A failed write never truncates
    the previous file. (Full D11 contract — exclusive temp, parent-dir fsync — is Slice 2.)"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # noqa: PTH105 - the failure test monkeypatches os.replace;
        #                        Path.replace would defeat that injection. Keep os.replace.
    finally:
        tmp.unlink(missing_ok=True)


def write_csv(path: Path, records: list[Any], fieldnames: list[str]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(asdict(record))
    atomic_write_text(path, buffer.getvalue())




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


def json_for_html(value: Any) -> str:
    """Serialize JSON safely for embedding inside an HTML script element."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


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

    template = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ScoutingEvent Merit Badge / Schedule Report</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #f4f6f8;
  --panel: #ffffff;
  --panel-alt: #eef3f6;
  --text: #17212b;
  --muted: #5e6b78;
  --border: #d3dbe3;
  --accent: #245b78;
  --accent-2: #dbeaf2;
  --success: #176b3a;
  --success-bg: #dff2e7;
  --warn: #8a4b08;
  --warn-bg: #fff0d8;
  --danger: #9b1c1c;
  --danger-bg: #fde5e5;
  --shadow: 0 2px 10px rgba(18, 38, 54, 0.08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111820;
    --panel: #18222d;
    --panel-alt: #202d39;
    --text: #ecf2f7;
    --muted: #aab7c4;
    --border: #334353;
    --accent: #70b6db;
    --accent-2: #203d4d;
    --success: #8fe0ad;
    --success-bg: #173b26;
    --warn: #ffd08a;
    --warn-bg: #4a3214;
    --danger: #ffaaaa;
    --danger-bg: #4b2222;
    --shadow: none;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.45;
}
header {
  background: linear-gradient(135deg, #173f57, #28739a);
  color: white;
  padding: 1.5rem clamp(1rem, 4vw, 3rem);
}
header h1 { margin: 0; font-size: clamp(1.55rem, 3vw, 2.35rem); }
header p { margin: .35rem 0 0; opacity: .9; }
header p#generated-at { font-size: 1.05rem; font-weight: 700; }
header p#generated-at.stale { color: #ffd6d6; }
.header-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; margin-top: .9rem; }
.header-actions button { width: auto; background: rgba(255,255,255,.12); color: white; border-color: rgba(255,255,255,.4); }
.header-actions button:hover { border-color: white; }
.header-actions #email-status { opacity: .9; font-size: .85rem; }
main { max-width: 1500px; margin: 0 auto; padding: 1rem; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: .75rem;
  margin-bottom: 1rem;
}
.summary-card, .panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
}
.summary-card { padding: .9rem 1rem; }
.summary-card .value { font-size: 1.6rem; font-weight: 750; }
.summary-card .label { color: var(--muted); font-size: .85rem; }
.panel { padding: 1rem; margin-bottom: 1rem; }
.controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
  gap: .75rem;
  align-items: end;
}
.control label { display: block; font-size: .78rem; font-weight: 700; color: var(--muted); margin-bottom: .25rem; }
input, select, button {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel);
  color: var(--text);
  padding: .62rem .7rem;
  font: inherit;
}
.checkbox-control { align-self: end; }
.checkbox-control[hidden] { display: none; }
.checkbox-label {
  display: flex !important;
  align-items: center;
  gap: .55rem;
  min-height: 45px;
  margin: 0 !important;
  padding: .55rem .7rem;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel-alt);
  color: var(--text) !important;
  cursor: pointer;
}
.checkbox-label input {
  width: auto;
  margin: 0;
  padding: 0;
  accent-color: var(--accent);
}
.checkbox-label span { line-height: 1.25; }
button { cursor: pointer; font-weight: 700; }
button:hover { border-color: var(--accent); }
.tabs { display: flex; gap: .4rem; flex-wrap: wrap; margin-bottom: 1rem; }
.tabs button { width: auto; padding-inline: 1rem; }
.tabs button.active { background: var(--accent); color: white; border-color: var(--accent); }
.view[hidden] { display: none; }
.result-count { color: var(--muted); margin: 0 0 .75rem; }
.scout-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: .9rem;
  overflow: hidden;
}
.scout-card > h2 {
  margin: 0;
  padding: .85rem 1rem;
  background: var(--panel-alt);
  border-bottom: 1px solid var(--border);
  font-size: 1.1rem;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.scout-card h2 small { color: var(--muted); font-weight: 500; }
.class-list { display: grid; }
.class-row {
  display: grid;
  grid-template-columns: 105px 85px minmax(260px, 2fr) 130px minmax(170px, 1fr) auto;
  gap: .7rem;
  align-items: center;
  padding: .7rem 1rem;
  border-bottom: 1px solid var(--border);
}
.class-row:last-child { border-bottom: 0; }
.class-row:hover { background: var(--panel-alt); }
.class-name { font-weight: 720; }
.meta { color: var(--muted); font-size: .86rem; }
.badge {
  display: inline-block;
  padding: .16rem .5rem;
  border-radius: 999px;
  font-size: .76rem;
  font-weight: 750;
  white-space: nowrap;
}
.badge.success { color: var(--success); background: var(--success-bg); }
.badge.warn { color: var(--warn); background: var(--warn-bg); }
.badge.danger { color: var(--danger); background: var(--danger-bg); }
.badge.check { color: var(--warn); background: var(--warn-bg); border: 1px solid var(--warn); }
details.requirements { grid-column: 1 / -1; }
details.requirements summary { cursor: pointer; color: var(--accent); font-weight: 700; }
.requirement-list { margin: .6rem 0 0; padding: 0; list-style: none; }
.requirement-list li { border-top: 1px solid var(--border); padding: .5rem 0; }
.requirement-number { font-weight: 750; margin-right: .35rem; }
.table-wrap { overflow: auto; max-height: 72vh; border: 1px solid var(--border); border-radius: 8px; }
table { border-collapse: separate; border-spacing: 0; width: 100%; min-width: 920px; background: var(--panel); }
th, td { text-align: left; padding: .62rem .7rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--panel-alt);
  font-size: .8rem;
  text-transform: uppercase;
  letter-spacing: .03em;
  cursor: pointer;
  user-select: none;
}
th.sorted::after { content: "  ▲"; }
th.sorted.desc::after { content: "  ▼"; }
tr:hover td { background: var(--panel-alt); }
.empty { padding: 2rem; text-align: center; color: var(--muted); }
.error-box { border-left: 4px solid var(--danger); background: var(--danger-bg); padding: .75rem 1rem; margin-top: 1rem; }
@media (max-width: 900px) {
  .class-row { grid-template-columns: 90px 70px 1fr; }
  .class-row > :nth-child(4), .class-row > :nth-child(5), .class-row > :nth-child(6) { grid-column: 3; }
  .controls { grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: .5rem; }
  input, select, button { padding: .45rem .55rem; font-size: .85rem; }
}
@media (max-width: 600px), (max-height: 500px) {
  .controls { grid-template-columns: 1fr 1fr; gap: .4rem; }
  input, select, button { padding: .35rem .45rem; font-size: .8rem; }
}
@media print {
  body { background: white; color: black; }
  header { background: white; color: black; padding: 0 0 1rem; }
  .controls, .tabs, #classes-view, #requirements-view { display: none !important; }
  main { max-width: none; padding: 0; }
  .panel, .scout-card { box-shadow: none; break-inside: avoid; }
}
</style>
</head>
<body>
<header>
  <h1>ScoutingEvent Merit Badge / Schedule Report</h1>
  <p id="generated-at"></p>
  <div class="header-actions">
    <button id="generate-emails-btn" type="button">Generate missing-requirement emails</button>
    <button id="open-emails-folder-btn" type="button">Open emails folder</button>
    <span id="email-status"></span>
  </div>
</header>
<main>
  <section class="summary-grid" id="summary"></section>

  <section class="panel">
    <div class="controls">
      <div class="control">
        <label for="search">Search</label>
        <input id="search" type="search" placeholder="Scout, class, number, location…">
      </div>
      <div class="control">
        <label for="scout-filter">Scout</label>
        <select id="scout-filter"><option value="">All scouts</option></select>
      </div>
      <div class="control">
        <label for="class-filter">Class</label>
        <select id="class-filter"><option value="">All classes</option></select>
      </div>
      <div class="control">
        <label for="block-filter">Block</label>
        <select id="block-filter"><option value="">All blocks</option></select>
      </div>
      <div class="control">
        <label for="day-filter">Day</label>
        <select id="day-filter"><option value="">All days</option></select>
      </div>
      <div class="control">
        <label for="location-filter">Location</label>
        <select id="location-filter"><option value="">All locations</option></select>
      </div>
      <div class="control">
        <label for="completion-filter">Completion</label>
        <select id="completion-filter">
          <option value="">All</option>
          <option value="complete">Completed classes</option>
          <option value="incomplete">Incomplete classes</option>
        </select>
      </div>
      <div class="control checkbox-control" id="completed-requirements-control" hidden>
        <label class="checkbox-label" for="show-completed-requirements">
          <input id="show-completed-requirements" type="checkbox">
          <span>Show completed requirements in incomplete classes</span>
        </label>
      </div>
      <div class="control checkbox-control">
        <label class="checkbox-label" for="prereq-filter">
          <input id="prereq-filter" type="checkbox">
          <span>Show only (pre-req) requirements</span>
        </label>
      </div>
      <div class="control">
        <label for="sort-select">Sort scout schedules</label>
        <select id="sort-select">
          <option value="time">Start time</option>
          <option value="class">Class name</option>
          <option value="block">Block</option>
          <option value="location">Location</option>
        </select>
      </div>
      <div class="control"><label>&nbsp;</label><button id="reset">Reset filters</button></div>
    </div>
  </section>

  <nav class="tabs" aria-label="Report views">
    <button class="active" data-view="scouts-view">By Scout</button>
    <button data-view="classes-view">All Classes</button>
    <button data-view="requirements-view">Requirements</button>
  </nav>

  <section id="scouts-view" class="view">
    <p class="result-count" id="scout-count"></p>
    <div id="scout-results"></div>
  </section>

  <section id="classes-view" class="view" hidden>
    <p class="result-count" id="class-count"></p>
    <div class="table-wrap">
      <table id="classes-table">
        <thead><tr>
          <th data-key="scout_name">Scout</th>
          <th data-key="start_time_24h">Time</th>
          <th data-key="days">Days</th>
          <th data-key="period_name">Block</th>
          <th data-key="class_name">Class</th>
          <th data-key="class_number">Class #</th>
          <th data-key="location">Location</th>
          <th data-key="class_completed">Status</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </section>

  <section id="requirements-view" class="view" hidden>
    <p class="result-count" id="requirement-count"></p>
    <div class="table-wrap">
      <table id="requirements-table">
        <thead><tr>
          <th data-key="scout_name">Scout</th>
          <th data-key="merit_badge_name">Class</th>
          <th data-key="class_number">Class #</th>
          <th data-key="requirement_number">Requirement</th>
          <th data-key="description">Description</th>
          <th data-key="present_days">Days</th>
          <th data-key="completed_requirement">Complete</th>
          <th data-key="requirement_on_event">At Event</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </section>

  <section id="errors"></section>
</main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const classes = data.classes || [];
  const requirements = data.requirements || [];
  const scouts = data.scouts || [];
  const dayOrder = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  const dayLabels = {Mo:"Monday", Tu:"Tuesday", We:"Wednesday", Th:"Thursday", Fr:"Friday", Sa:"Saturday", Su:"Sunday"};
  const state = { classSort: {key:"scout_name", desc:false}, reqSort: {key:"scout_name", desc:false} };

  const $ = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const boolBadge = (value, yes="Complete", no="Incomplete") => value
    ? `<span class="badge success">${escapeHtml(yes)}</span>`
    : `<span class="badge warn">${escapeHtml(no)}</span>`;
  const requirementBadge = item => {
    const reason = escapeHtml(item.calculated_status_reason || "");
    if (item.calculated_status === "complete") {
      return `<span class="badge success" title="${reason}">Completed</span>`;
    }
    if (item.calculated_status === "complete_check") {
      return `<span class="badge check" title="${reason}">Completed, but double check</span>`;
    }
    return `<span class="badge warn" title="${reason}">Not complete</span>`;
  };
  const requirementIsComplete = item => ["complete", "complete_check"].includes(item.calculated_status);
  const isPrereqRequirement = item => normalize(item.description).includes("(pre-req)");
  const tokensForDays = value => dayOrder.filter(token => String(value || "").includes(token));
  const normalize = value => String(value ?? "").trim().toLocaleLowerCase();
  const uniqueSorted = values => [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b, undefined, {numeric:true}));
  const reqKey = item => `${item.scout_name}\u0000${item.class_p4_id}`;
  const requirementsByClass = new Map();
  for (const req of requirements) {
    const key = reqKey(req);
    if (!requirementsByClass.has(key)) requirementsByClass.set(key, []);
    requirementsByClass.get(key).push(req);
  }

  const generatedEl = $("generated-at");
  generatedEl.textContent = `Generated ${data.generated_at_local || ""}`;
  if (data.generated_at_iso) {
    const ageMs = Math.abs(Date.now() - new Date(data.generated_at_iso).getTime());
    if (Number.isFinite(ageMs) && ageMs > 4 * 60 * 60 * 1000) {
      generatedEl.classList.add("stale");
      generatedEl.insertAdjacentHTML("beforeend", ` — <strong>this report may be out of date; consider re-running it.</strong>`);
    }
  }

  const emailStatusEl = $("email-status");
  const generateEmailsBtn = $("generate-emails-btn");
  const openEmailsFolderBtn = $("open-emails-folder-btn");

  async function apiPost(path) {
    const response = await fetch(path, { method: "POST" });
    let body = null;
    try { body = await response.json(); } catch { /* ignore */ }
    if (!response.ok) {
      throw new Error(body?.detail || `${response.status} ${response.statusText}`);
    }
    return body;
  }

  generateEmailsBtn.addEventListener("click", async () => {
    generateEmailsBtn.disabled = true;
    emailStatusEl.textContent = "Generating emails…";
    try {
      const result = await apiPost(`/api/runs/${encodeURIComponent(data.run_id || "")}/generate-emails`);
      emailStatusEl.textContent =
        `${result.scouts_needing_email} scout(s) need an email, ${result.scouts_all_complete} fully complete.`;
    } catch (err) {
      emailStatusEl.textContent =
        "Could not generate emails. Open this report through the Scout Schedule app to use this feature.";
    } finally {
      generateEmailsBtn.disabled = false;
    }
  });

  openEmailsFolderBtn.addEventListener("click", async () => {
    openEmailsFolderBtn.disabled = true;
    try {
      await apiPost(`/api/runs/${encodeURIComponent(data.run_id || "")}/open-emails-folder`);
      emailStatusEl.textContent = "Opened the emails folder.";
    } catch (err) {
      emailStatusEl.textContent = /not.*generated/i.test(err.message)
        ? "Generate emails first."
        : "Could not open the emails folder. Open this report through the Scout Schedule app to use this feature.";
    } finally {
      openEmailsFolderBtn.disabled = false;
    }
  });

  $("summary").innerHTML = [
    [scouts.length, "Scouts"],
    [classes.length, "Scheduled classes"],
    [requirements.length, "Requirements"],
    [data.errors?.length || 0, "Errors"]
  ].map(([value,label]) => `<div class="summary-card"><div class="value">${value}</div><div class="label">${label}</div></div>`).join("");

  function fillSelect(id, values, labels = null) {
    const select = $(id);
    for (const value of values) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = labels?.[value] || value;
      select.appendChild(option);
    }
  }
  fillSelect("scout-filter", uniqueSorted(scouts.map(s => s.name)));
  fillSelect("class-filter", uniqueSorted(classes.map(c => c.class_name)));
  fillSelect("block-filter", uniqueSorted(classes.map(c => c.period_name)));
  fillSelect("day-filter", dayOrder.filter(day => classes.some(c => tokensForDays(c.days).includes(day))), dayLabels);
  fillSelect("location-filter", uniqueSorted(classes.map(c => c.location)));

  function filters() {
    return {
      search: normalize($("search").value), scout: $("scout-filter").value,
      className: $("class-filter").value, block: $("block-filter").value,
      day: $("day-filter").value, location: $("location-filter").value,
      completion: $("completion-filter").value,
      showCompletedRequirements: $("show-completed-requirements").checked,
      prereqOnly: $("prereq-filter").checked
    };
  }

  function classMatches(item, f = filters()) {
    const haystack = normalize([item.scout_name, item.class_name, item.class_number, item.location, item.period_name, item.days].join(" "));
    return (!f.search || haystack.includes(f.search))
      && (!f.scout || item.scout_name === f.scout)
      && (!f.className || item.class_name === f.className)
      && (!f.block || item.period_name === f.block)
      && (!f.day || tokensForDays(item.days).includes(f.day))
      && (!f.location || item.location === f.location)
      && (!f.completion || (f.completion === "complete") === Boolean(item.class_completed));
  }

  function requirementMatches(item, f = filters()) {
    const linkedClass = classes.find(c => c.scout_name === item.scout_name && c.class_p4_id === item.class_p4_id);
    const haystack = normalize([item.scout_name, item.merit_badge_name, item.class_number, item.requirement_number, item.description, item.present_days].join(" "));
    return (!f.search || haystack.includes(f.search))
      && (!f.scout || item.scout_name === f.scout)
      && (!f.className || item.merit_badge_name === f.className || linkedClass?.class_name === f.className)
      && (!f.block || linkedClass?.period_name === f.block)
      && (!f.day || tokensForDays(item.present_days).includes(f.day) || tokensForDays(linkedClass?.days).includes(f.day))
      && (!f.location || linkedClass?.location === f.location)
      && (!f.completion || (f.completion === "complete") === Boolean(item.completed_class))
      && (!(f.completion === "incomplete" && !f.showCompletedRequirements) || !requirementIsComplete(item))
      && (!f.prereqOnly || isPrereqRequirement(item));
  }

  function compareValues(a, b, key, desc) {
    let av = a[key], bv = b[key];
    if (typeof av === "boolean" || typeof bv === "boolean") { av = Number(Boolean(av)); bv = Number(Boolean(bv)); }
    const result = String(av ?? "").localeCompare(String(bv ?? ""), undefined, {numeric:true, sensitivity:"base"});
    return desc ? -result : result;
  }

  function renderScouts() {
    const f = filters();
    const sortKey = $("sort-select").value;
    const sortMap = {time:"start_time_24h", class:"class_name", block:"period_name", location:"location"};
    const grouped = new Map();
    for (const item of classes.filter(c => classMatches(c, f))) {
      if (!grouped.has(item.scout_name)) grouped.set(item.scout_name, []);
      grouped.get(item.scout_name).push(item);
    }
    const scoutNames = [...grouped.keys()].sort((a,b) => a.localeCompare(b));
    $("scout-count").textContent = `${scoutNames.length} scout(s), ${[...grouped.values()].reduce((n,v)=>n+v.length,0)} matching class(es)`;
    if (!scoutNames.length) {
      $("scout-results").innerHTML = '<div class="panel empty">No classes match the current filters.</div>';
      return;
    }
    $("scout-results").innerHTML = scoutNames.map(name => {
      const rows = grouped.get(name).slice().sort((a,b) => compareValues(a,b,sortMap[sortKey],false) || compareValues(a,b,"class_name",false));
      const content = rows.map(item => {
        const allReqs = requirementsByClass.get(reqKey(item)) || [];
        const hideCompleted = f.completion === "incomplete" && !f.showCompletedRequirements;
        let reqs = hideCompleted ? allReqs.filter(req => !requirementIsComplete(req)) : allReqs;
        if (f.prereqOnly) reqs = reqs.filter(isPrereqRequirement);
        const hiddenCount = allReqs.length - reqs.length;
        let reqHtml = "";
        if (allReqs.length) {
          const hiddenText = hiddenCount ? `; ${hiddenCount} hidden` : "";
          const reqBody = reqs.length
            ? `<ul class="requirement-list">${reqs.map(req => `<li><span class="requirement-number">${escapeHtml(req.requirement_number)}</span>${escapeHtml(req.description)} ${requirementBadge(req)}</li>`).join("")}</ul>`
            : `<p class="meta">No requirement rows match the current filters.</p>`;
          const completedCount = reqs.filter(requirementIsComplete).length;
          const prereqIncompleteCount = reqs.filter(req => !requirementIsComplete(req) && isPrereqRequirement(req)).length;
          const incompleteCount = reqs.length - completedCount - prereqIncompleteCount;
          reqHtml = `<details class="requirements"><summary>${reqs.length} visible requirement row(s), ${completedCount} completed, ${incompleteCount} incomplete, ${prereqIncompleteCount} incomplete (pre-reqs)${hiddenText}</summary>${reqBody}</details>`;
        }
        return `<div class="class-row">
          <div><strong>${escapeHtml(item.start_time)}</strong></div>
          <div>${escapeHtml(item.days)}</div>
          <div><div class="class-name">${escapeHtml(item.class_name)}</div><div class="meta">${escapeHtml(item.class_number)}</div></div>
          <div>${escapeHtml(item.period_name)}</div>
          <div>${escapeHtml(item.location)}</div>
          <div>${boolBadge(item.class_completed)}</div>
          ${reqHtml}
        </div>`;
      }).join("");
      return `<article class="scout-card"><h2><span>${escapeHtml(name)}</span><small>${rows.length} class(es)</small></h2><div class="class-list">${content}</div></article>`;
    }).join("");
  }

  function renderClasses() {
    const rows = classes.filter(item => classMatches(item)).slice().sort((a,b) => compareValues(a,b,state.classSort.key,state.classSort.desc));
    $("class-count").textContent = `${rows.length} matching class row(s)`;
    $("classes-table").querySelector("tbody").innerHTML = rows.map(item => `<tr>
      <td>${escapeHtml(item.scout_name)}</td><td>${escapeHtml(item.start_time)}</td><td>${escapeHtml(item.days)}</td>
      <td>${escapeHtml(item.period_name)}</td><td><strong>${escapeHtml(item.class_name)}</strong></td>
      <td>${escapeHtml(item.class_number)}</td><td>${escapeHtml(item.location)}</td><td>${boolBadge(item.class_completed)}</td>
    </tr>`).join("") || '<tr><td colspan="8" class="empty">No classes match the current filters.</td></tr>';
    updateSortHeaders("classes-table", state.classSort);
  }

  function renderRequirements() {
    const rows = requirements.filter(item => requirementMatches(item)).slice().sort((a,b) => compareValues(a,b,state.reqSort.key,state.reqSort.desc));
    $("requirement-count").textContent = `${rows.length} matching requirement row(s)`;
    $("requirements-table").querySelector("tbody").innerHTML = rows.map(item => `<tr>
      <td>${escapeHtml(item.scout_name)}</td><td>${escapeHtml(item.merit_badge_name)}</td><td>${escapeHtml(item.class_number)}</td>
      <td><strong>${escapeHtml(item.requirement_number)}</strong></td><td>${escapeHtml(item.description).replaceAll("\n", "<br>")}</td>
      <td>${escapeHtml(item.present_days)}</td><td>${requirementBadge(item)}</td>
      <td>${boolBadge(item.requirement_on_event, "Yes", "No")}</td>
    </tr>`).join("") || '<tr><td colspan="8" class="empty">No requirements match the current filters.</td></tr>';
    updateSortHeaders("requirements-table", state.reqSort);
  }

  function updateSortHeaders(tableId, sort) {
    for (const th of $(tableId).querySelectorAll("th[data-key]")) {
      th.classList.toggle("sorted", th.dataset.key === sort.key);
      th.classList.toggle("desc", th.dataset.key === sort.key && sort.desc);
    }
  }

  function syncCompletedRequirementsControl() {
    $("completed-requirements-control").hidden = $("completion-filter").value !== "incomplete";
  }

  function renderAll() {
    syncCompletedRequirementsControl();
    renderScouts();
    renderClasses();
    renderRequirements();
  }
  for (const id of ["search","scout-filter","class-filter","block-filter","day-filter","location-filter","completion-filter","sort-select","show-completed-requirements","prereq-filter"]) {
    $(id).addEventListener(id === "search" ? "input" : "change", renderAll);
  }
  $("reset").addEventListener("click", () => {
    for (const id of ["search","scout-filter","class-filter","block-filter","day-filter","location-filter","completion-filter"]) $(id).value = "";
    $("show-completed-requirements").checked = false;
    $("prereq-filter").checked = false;
    $("sort-select").value = "time";
    renderAll();
  });
  for (const button of document.querySelectorAll(".tabs button")) {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b === button));
      document.querySelectorAll(".view").forEach(view => view.hidden = view.id !== button.dataset.view);
    });
  }
  for (const [tableId, sortState] of [["classes-table", state.classSort], ["requirements-table", state.reqSort]]) {
    for (const th of $(tableId).querySelectorAll("th[data-key]")) {
      th.addEventListener("click", () => {
        if (sortState.key === th.dataset.key) sortState.desc = !sortState.desc;
        else { sortState.key = th.dataset.key; sortState.desc = false; }
        tableId === "classes-table" ? renderClasses() : renderRequirements();
      });
    }
  }
  if (data.errors?.length) {
    $("errors").innerHTML = `<div class="error-box"><strong>${data.errors.length} extraction error(s)</strong><ul>${data.errors.map(e => `<li>${escapeHtml(e.scout_name)}: ${escapeHtml(e.error)}</li>`).join("")}</ul></div>`;
  }
  renderAll();
})();
</script>
</body>
</html>
'''
    atomic_write_text(
        path,
        template.replace("__REPORT_DATA__", json_for_html(report_data)),
        encoding="utf-8",
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
    run_identity = run_identity or RunIdentity()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = output_dir.name
    classes = [item for result in results for item in result.classes]
    requirements = [item for result in results for item in result.requirements]
    generated_at_local = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    generated_at_iso = datetime.now().astimezone().isoformat(timespec="seconds")

    nested = []
    for result in results:
        nested.append(
            {
                "name": result.name,
                "qr_url": result.qr_url,
                "attendee_id": result.attendee_id,
                "classes": [asdict(item) for item in result.classes],
                "requirements": [asdict(item) for item in result.requirements],
                "errors": result.errors,
            }
        )
    atomic_write_text(
        output_dir / "scouts.json",
        json.dumps(nested, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    write_csv(
        output_dir / "classes.csv",
        classes,
        [field.name for field in ClassRecord.__dataclass_fields__.values()],
    )
    write_csv(
        output_dir / "requirements.csv",
        requirements,
        [field.name for field in RequirementRecord.__dataclass_fields__.values()],
    )

    error_rows = [
        {"scout_name": result.name, "attendee_id": result.attendee_id, "error": error}
        for result in results
        for error in result.errors
    ]
    error_buffer = io.StringIO()
    error_writer = csv.DictWriter(error_buffer, fieldnames=["scout_name", "attendee_id", "error"])
    error_writer.writeheader()
    error_writer.writerows(error_rows)
    atomic_write_text(output_dir / "errors.csv", error_buffer.getvalue())

    safe_html_name = Path(html_name).name or "report.html"
    if not safe_html_name.lower().endswith(".html"):
        safe_html_name += ".html"
    if generate_html:
        write_html_report(
            output_dir / safe_html_name, results, generated_at_local, generated_at_iso, run_id=run_id
        )

    email_report_dir = (
        write_email_reports(output_dir, nested, run_identity=run_identity).name
        if generate_email_report
        else None
    )

    summary = {
        "scouts_processed": len(results),
        "scouts_with_errors": sum(1 for result in results if result.errors),
        "classes": len(classes),
        "requirements": len(requirements),
        "generated_at_local": generated_at_local,
        "generated_at_iso": generated_at_iso,
        "html_report": safe_html_name if generate_html else None,
        "email_report_dir": email_report_dir,
    }
    atomic_write_text(output_dir / "summary.json", json.dumps(summary, indent=2), encoding="utf-8")


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
