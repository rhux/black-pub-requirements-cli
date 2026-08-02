"""Report and email composition, and sink orchestration.

The reporting counterpart to features/ingest/service.py: this feature owns POLICY -- which
artifacts one run produces, how the HTML report and per-scout emails are composed from the raw
records, and where each write is routed. Every write goes through the injected ArtifactSink,
never through the atomic-write adapter directly; that is what keeps this module importable
without pulling in an adapter (enforced by tests/architecture's dependency-rule test).

The requirement-status/missing-requirement/email-copy helpers below duplicate
scout_schedule_cli.py's same-named functions rather than importing them: that script sits
OUTSIDE the package and depends on it (scout_schedule_cli.py imports from scoutmb, never the
reverse), so a package module importing back from the script would be circular. The script's
copies stay in place, unchanged, because a large existing test surface
(tests/characterization/test_phase_a_gap_closure.py, tests/privacy/test_surface_policies.py,
tests/unit/test_output_filenames.py, tests/unit/test_run_identity_scope.py, tools/gen_golden.py,
ui/server.py, ...) calls them directly as module attributes. Both copies must be kept in
lockstep by inspection -- tests/parity/test_output_parity.py is what would notice drift.
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scoutmb.core.identity import AttendeeId, MissingAttendeeId, RunIdentity, attendee_filename_stem
from scoutmb.core.inference.missing import group_missing_requirements
from scoutmb.core.inference.status import calculate_statuses
from scoutmb.core.inference.tree import build_group_tree
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult
from scoutmb.core.output_schemas import class_to_row, requirement_to_row
from scoutmb.ports.artifact_sink import ArtifactSink, ReportRenderer


def _attendee_key_for(item: Mapping[str, Any]) -> str:
    """Grouping identity: prefers output_id (the shareable report's rows), falls back to
    attendee_id (the operational `nested` rows this same helper also groups via
    _build_missing_requirements), then display name -- two attendees can share a name, and
    merging them would silently corrupt both. Mirrors scout_schedule_cli._attendee_key_for's
    attendee_id-or-name fallback, extended with output_id so it also works on shareable rows
    where attendee_id has already been projected away.

    The name-based fallback is only safe because of an invariant enforced elsewhere, not here:
    scout_schedule_cli.process_scout always sets attendee_id before populating
    classes/requirements, so a blank-identity ScoutResult is assumed to always carry empty
    collections -- two same-named blank-identity attendees can then never actually reach this
    function carrying real requirement data to collide over. `publish` below asserts that
    invariant (`_assert_blank_identity_has_no_records`) before any result reaches this
    grouping, since nothing in this function itself can tell two same-named collisions apart.
    """
    identity = item.get("output_id")
    if identity is None:
        identity = item.get("attendee_id")
    identity = str(identity or "").strip()
    if identity:
        return identity
    return f"name:{str(item.get('scout_name') or '')}"


def _assert_blank_identity_has_no_records(results: Sequence[ScoutResult]) -> None:
    """Fail loudly if a blank-identity ScoutResult carries class/requirement data.

    `_attendee_key_for`'s `f"name:{scout_name}"` fallback is only safe because
    scout_schedule_cli.process_scout always sets attendee_id BEFORE populating
    classes/requirements (a ScoutResult that failed before identity resolution is assumed to
    always have empty collections). That invariant lives in a different file and nothing here
    enforces it -- if it were ever violated, two different same-named attendees with blank
    identity would silently merge into one inferred requirement structure in report.html/the
    missing-requirement emails, with no exception and no warning. Matches this codebase's
    "loud failure over silent leak" philosophy elsewhere (e.g. tools/gen_golden.py's unseeded-
    UUID assertion, scoutmb.errors.CapabilityUnavailable).
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
                "merging their data -- refusing to publish instead."
            )


def _resolve_output_id(attendee_id: str, scout_name: str, run_identity: RunIdentity) -> str | None:
    """None for an attempt that failed before identity resolution (process_scout can build a
    ScoutResult with attendee_id == "" before ever reading it); never a placeholder string."""
    try:
        return run_identity.output_id(AttendeeId.parse(attendee_id, scout_name))
    except MissingAttendeeId:
        return None


def _annotate_requirement_statuses(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add inferred display status fields used only by the HTML report.

    Mirrors scout_schedule_cli.annotate_requirement_statuses; see that function's docstring
    for the rationale.
    """
    annotated = [dict(item) for item in requirements]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in annotated:
        grouped.setdefault(
            (_attendee_key_for(item), str(item.get("class_p4_id") or "")), []
        ).append(item)

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


def _clean_html_description(value: str) -> str:
    """Mirrors scout_schedule_cli.clean_html_description exactly."""
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _build_missing_requirements(scouts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mirrors scout_schedule_cli.build_missing_requirements exactly."""
    flattened = [dict(req) for scout in scouts for req in scout.get("requirements", [])]
    annotated = _annotate_requirement_statuses(flattened)
    return group_missing_requirements(
        annotated,
        attendee_key_of=_attendee_key_for,
        clean_description=_clean_html_description,
    )


def _email_subject(scout_name: str) -> str:
    return f"Merit Badge Requirements Still Needed - {scout_name}"


def _render_email_text(scout_name: str, badge_groups: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        f"Hi {scout_name},",
        "",
        "Here are the merit badge requirements you still need to complete:",
    ]
    for badge_name, items in badge_groups.items():
        lines.append("")
        lines.append(badge_name)
        lines.append("-" * len(badge_name))
        for item in items:
            indent = "  " * (item["depth"] + 1)
            prefix = (
                f"{indent}{item['requirement_number']}. " if item["requirement_number"] else indent
            )
            body = item["description"].replace("\n", "\n" + " " * len(prefix))
            line = f"{prefix}{body}"
            if item["is_prereq"]:
                line += " (complete before the event)"
            lines.append(line)
    lines.append("")
    lines.append(
        "Please work with your merit badge counselor to complete these. Reach out if you have questions."
    )
    return "\n".join(lines)


def _render_email_html(scout_name: str, badge_groups: dict[str, list[dict[str, Any]]]) -> str:
    sections = []
    for badge_name, items in badge_groups.items():
        rows = []
        for item in items:
            number = html.escape(item["requirement_number"])
            description = html.escape(item["description"]).replace("\n", "<br>")
            prereq_badge = (
                ' <span class="prereq">complete before the event</span>'
                if item["is_prereq"]
                else ""
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


@dataclass(frozen=True, slots=True)
class ReportingService:
    """Composes the operational report/email artifacts for one run and hands each to the
    injected sink. Timestamps and the RunIdentity are parameters, never read/constructed here:
    exactly one RunIdentity exists per run (D... see core/identity.py) and must be threaded in
    by the caller, and deterministic timestamps are what makes this service's output
    comparable byte-for-byte in tests."""

    sink: ArtifactSink
    renderer: ReportRenderer

    def publish(
        self,
        output_dir: Path,
        results: Sequence[ScoutResult],
        *,
        generated_at_local: str,
        generated_at_iso: str,
        run_identity: RunIdentity,
        generate_html: bool = True,
        html_name: str = "report.html",
        generate_email_report: bool = False,
    ) -> None:
        _assert_blank_identity_has_no_records(results)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_id = output_dir.name
        classes = [item for result in results for item in result.classes]
        requirements = [item for result in results for item in result.requirements]

        nested = [
            {
                "name": result.name,
                "qr_url": result.qr_url,
                "attendee_id": result.attendee_id,
                "classes": [asdict(item) for item in result.classes],
                "requirements": [asdict(item) for item in result.requirements],
                "errors": list(result.errors),
            }
            for result in results
        ]
        self.sink.publish_text(
            output_dir / "scouts.json",
            json.dumps(nested, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self.sink.publish_rows(
            output_dir / "classes.csv",
            classes,
            [field.name for field in ClassRecord.__dataclass_fields__.values()],
        )
        self.sink.publish_rows(
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
        error_writer = csv.DictWriter(
            error_buffer, fieldnames=["scout_name", "attendee_id", "error"]
        )
        error_writer.writeheader()
        error_writer.writerows(error_rows)
        self.sink.publish_text(output_dir / "errors.csv", error_buffer.getvalue())

        safe_html_name = Path(html_name).name or "report.html"
        if not safe_html_name.lower().endswith(".html"):
            safe_html_name += ".html"
        if generate_html:
            report_data = self._report_data(
                results, generated_at_local, generated_at_iso, run_id, run_identity
            )
            self.sink.publish_text(
                output_dir / safe_html_name, self.renderer(report_data), encoding="utf-8"
            )

        email_report_dir = (
            self._write_email_reports(output_dir, nested, run_identity=run_identity).name
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
        self.sink.publish_text(
            output_dir / "summary.json", json.dumps(summary, indent=2), encoding="utf-8"
        )

    def _report_data(
        self,
        results: Sequence[ScoutResult],
        generated_at_local: str,
        generated_at_iso: str,
        run_id: str,
        run_identity: RunIdentity,
    ) -> dict[str, Any]:
        """report.html is the shareable surface: every row here carries output_id, never
        attendee_id/qr_url. One output_id is resolved per ScoutResult (RunIdentity.output_id is
        idempotent per attendee, so every class/requirement/error/scout row for the same
        attendee gets the same value) and substituted in place via class_to_row/
        requirement_to_row's shareable=True projection.
        """
        classes: list[dict[str, Any]] = []
        requirements: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        scouts: list[dict[str, Any]] = []
        for result in results:
            output_id = _resolve_output_id(result.attendee_id, result.name, run_identity)
            classes.extend(
                class_to_row(item, shareable=True, output_id=output_id) for item in result.classes
            )
            requirements.extend(
                requirement_to_row(item, shareable=True, output_id=output_id)
                for item in result.requirements
            )
            errors.extend(
                {"scout_name": result.name, "output_id": output_id, "error": error}
                for error in result.errors
            )
            scouts.append(
                {
                    "name": result.name,
                    "output_id": output_id,
                    "class_count": len(result.classes),
                    "requirement_count": len(result.requirements),
                    "error_count": len(result.errors),
                }
            )
        requirements = _annotate_requirement_statuses(requirements)
        return {
            "generated_at_local": generated_at_local,
            "generated_at_iso": generated_at_iso,
            "run_id": run_id,
            "scouts": scouts,
            "classes": classes,
            "requirements": requirements,
            "errors": errors,
        }

    def _write_email_reports(
        self,
        output_dir: Path,
        scouts: list[dict[str, Any]],
        *,
        run_identity: RunIdentity,
    ) -> Path:
        """Write per-scout missing-requirement emails plus a combined mail-merge CSV."""
        emails_dir = output_dir / "emails"
        emails_dir.mkdir(parents=True, exist_ok=True)
        missing = _build_missing_requirements(scouts)

        fieldnames = [
            "scout_name",
            "attendee_id",
            "status",
            "merit_badge_count",
            "missing_requirement_count",
            "subject",
            "body_text",
            "body_html",
        ]
        csv_rows = []
        for scout in scouts:
            scout_name = str(scout.get("name") or "")
            attendee_id = str(scout.get("attendee_id") or "")
            attendee_key = attendee_id.strip() or f"unresolved-{scout_name}"
            bucket = missing.get(attendee_key) or {"display_name": scout_name, "badges": {}}
            badge_groups = bucket["badges"]
            missing_count = sum(
                1 for items in badge_groups.values() for item in items if item["is_leaf"]
            )

            if missing_count:
                status = "missing_requirements"
            elif not scout.get("requirements") and scout.get("errors"):
                status = "no_data_scraped"
            else:
                status = "all_complete"

            subject = _email_subject(scout_name)
            body_text = _render_email_text(scout_name, badge_groups) if missing_count else ""
            body_html = _render_email_html(scout_name, badge_groups) if missing_count else ""

            if missing_count:
                output_id = run_identity.output_id(AttendeeId.parse(attendee_id, scout_name))
                slug = attendee_filename_stem(scout_name, output_id)
                self.sink.publish_text(emails_dir / f"{slug}.txt", body_text, encoding="utf-8")
                self.sink.publish_text(emails_dir / f"{slug}.html", body_html, encoding="utf-8")

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
        self.sink.publish_text(emails_dir / "missing_requirements.csv", buffer.getvalue())

        return emails_dir
