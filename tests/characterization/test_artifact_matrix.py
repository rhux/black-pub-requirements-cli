"""Typed matrix execution of the artifact characterization catalog (Task 20).

Each ``ART-*`` case drives the REAL ``scout_schedule_cli`` output writers (never mocked, except
at the exact filesystem seams the ``ART-FAIL-*`` cases name). No test writes outside
``tmp_path`` and none performs real network I/O.

Each ``_ctx_*`` method returns an ``observed`` value computed from the real writer call;
``test_artifact_execution`` asserts ``observed == case.expected_by_context[context_id]`` -- one
clean equality per case, mirroring ``LegacyRequirementRunner`` in ``test_requirement_matrix.py``.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
from tests.matrix.cases.artifact_cases import ARTIFACT_CASES, ArtifactCase
from tests.matrix.pytest_support import execution_params


def _build_result(rows: tuple, root: Path):
    import scout_schedule_cli as legacy

    classes = [
        legacy.ClassRecord(
            **{k: v for k, v in row.items() if k in legacy.ClassRecord.__dataclass_fields__}
        )
        for row in rows
        if "class_name" in row
    ]
    requirements = [
        legacy.RequirementRecord(
            **{k: v for k, v in row.items() if k in legacy.RequirementRecord.__dataclass_fields__}
        )
        for row in rows
        if "requirement_number" in row
    ]
    return legacy.ScoutResult(
        name="Avery Example",
        qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id="90000001",
        classes=classes,
        requirements=requirements,
        errors=[],
    )


class LegacyArtifactRunner:
    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: ArtifactCase, *, root: Path) -> object:
        return getattr(self, f"_ctx_{self.context_id}")(case, root)

    # -- schema -----------------------------------------------------------------------------

    def _ctx_schema(self, case: ArtifactCase, root: Path) -> object:
        import scout_schedule_cli as legacy

        result = _build_result(case.input_rows, root)
        member = case.meta.member

        if member == "scouts-json":
            legacy.write_outputs(root, [result], generate_html=False)
            return json.loads((root / "scouts.json").read_text(encoding="utf-8"))
        if member == "classes-csv":
            legacy.write_outputs(root, [result], generate_html=False)
            text = (root / "classes.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = tuple(reader.fieldnames or ())
            rows = list(reader)
            return (fieldnames, len(rows), rows[0]["class_name"])
        if member == "requirements-csv":
            legacy.write_outputs(root, [result], generate_html=False)
            text = (root / "requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = tuple(reader.fieldnames or ())
            rows = list(reader)
            return (fieldnames, len(rows), rows[0]["requirement_number"])
        if member == "errors-csv":
            result.errors.append("boom")
            legacy.write_outputs(root, [result], generate_html=False)
            text = (root / "errors.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = list(reader.fieldnames or ())
            rows = list(reader)
            return (fieldnames, rows)
        if member == "summary-json":
            legacy.write_outputs(root, [result], generate_html=True)
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            return (
                frozenset(summary),
                summary["scouts_processed"],
                summary["classes"],
                summary["requirements"],
                summary["html_report"],
                summary["email_report_dir"],
            )
        if member == "report-data":
            legacy.write_outputs(root, [result], generate_html=True)
            html_text = (root / "report.html").read_text(encoding="utf-8")
            no_placeholder = "__REPORT_DATA__" not in html_text
            start = html_text.index('<script id="report-data" type="application/json">') + len(
                '<script id="report-data" type="application/json">'
            )
            end = html_text.index("</script>", start)
            payload = json.loads(html_text[start:end])
            return (
                no_placeholder,
                frozenset(payload),
                len(payload["classes"]),
                len(payload["requirements"]),
            )
        if member == "email-csv":
            nested = [
                {
                    "name": result.name,
                    "attendee_id": result.attendee_id,
                    "classes": [asdict(c) for c in result.classes],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": result.errors,
                }
            ]
            legacy.write_email_reports(root, nested)
            text = (root / "emails" / "missing_requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = tuple(reader.fieldnames or ())
            rows = list(reader)
            return (fieldnames, len(rows), rows[0]["status"])
        if member == "email-text-html":
            nested = [
                {
                    "name": result.name,
                    "attendee_id": result.attendee_id,
                    "classes": [asdict(c) for c in result.classes],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": result.errors,
                }
            ]
            legacy.write_email_reports(root, nested)
            emails_dir = root / "emails"
            txt_files = list(emails_dir.glob("*.txt"))
            html_files = list(emails_dir.glob("*.html"))
            txt_starts_with_greeting = (
                txt_files[0].read_bytes().decode("utf-8").startswith("Hi Avery Example,")
            )
            html_has_doctype = "<!doctype html>" in html_files[0].read_bytes().decode("utf-8")
            return (len(txt_files), len(html_files), txt_starts_with_greeting, html_has_doctype)
        raise AssertionError(f"unknown ART-SCHEMA member: {member}")

    # -- html -------------------------------------------------------------------------------

    def _ctx_html(self, case: ArtifactCase, root: Path) -> object:
        import scout_schedule_cli as legacy

        row = case.input_rows[0]
        description = str(row["description"])
        annotated = legacy.annotate_requirement_statuses([dict(row)])
        embedded = legacy.json_for_html({"requirements": annotated})

        script_tag_absent = "</script>" not in embedded
        escaped_lt = ("\\u003c" in embedded) if "<" in description else None
        escaped_gt = ("\\u003e" in embedded) if ">" in description else None
        escaped_amp = ("\\u0026" in embedded) if "&" in description else None
        escaped_u2028 = ("\\u2028" in embedded) if " " in description else None
        escaped_u2029 = ("\\u2029" in embedded) if " " in description else None
        literal_u2028_absent = (" " not in embedded) if " " in description else None
        literal_u2029_absent = (" " not in embedded) if " " in description else None
        non_ascii_literal_present = (
            ("Café" in embedded and "徽章" in embedded)
            if case.meta.member == "non-ascii-unicode"
            else None
        )

        decoded = json.loads(embedded)
        round_trip_matches = decoded["requirements"][0]["description"] == description

        return (
            script_tag_absent,
            escaped_lt,
            escaped_gt,
            escaped_amp,
            escaped_u2028,
            escaped_u2029,
            literal_u2028_absent,
            literal_u2029_absent,
            non_ascii_literal_present,
            round_trip_matches,
        )

    # -- email ------------------------------------------------------------------------------

    def _ctx_email(self, case: ArtifactCase, root: Path) -> object:
        import scout_schedule_cli as legacy

        member = case.meta.member
        if member == "missing-requirements":
            result = _build_result(case.input_rows, root)
            nested = [
                {
                    "name": result.name,
                    "attendee_id": result.attendee_id,
                    "classes": [],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": [],
                }
            ]
            legacy.write_email_reports(root, nested)
            emails_dir = root / "emails"
            return (len(list(emails_dir.glob("*.txt"))), len(list(emails_dir.glob("*.html"))))
        if member == "all-complete":
            result = _build_result(case.input_rows, root)
            nested = [
                {
                    "name": result.name,
                    "attendee_id": result.attendee_id,
                    "classes": [],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": [],
                }
            ]
            legacy.write_email_reports(root, nested)
            emails_dir = root / "emails"
            txt_count = len(list(emails_dir.glob("*.txt")))
            html_count = len(list(emails_dir.glob("*.html")))
            text = (emails_dir / "missing_requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            status = list(reader)[0]["status"]
            return (txt_count, html_count, status)
        if member == "no-data":
            nested = [
                {
                    "name": "Avery Example",
                    "attendee_id": "90000001",
                    "classes": [],
                    "requirements": [],
                    "errors": ["something failed"],
                }
            ]
            legacy.write_email_reports(root, nested)
            text = (root / "emails" / "missing_requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            status = list(reader)[0]["status"]
            return (status,)
        if member == "same-name-disambiguation":
            nested = [
                {
                    "name": "Avery Example",
                    "attendee_id": row["attendee_id"],
                    "classes": [],
                    "requirements": [dict(row, requirement_number="#1a")],
                    "errors": [],
                }
                for row in case.input_rows
            ]
            legacy.write_email_reports(root, nested)
            txt_files = sorted(p.name for p in (root / "emails").glob("*.txt"))
            return (len(txt_files), len(txt_files) == 2 and txt_files[0] != txt_files[1])
        raise AssertionError(f"unknown ART-EMAIL member: {member}")

    # -- filename ---------------------------------------------------------------------------

    def _ctx_filename(self, case: ArtifactCase, root: Path) -> object:
        import scout_schedule_cli as legacy

        member = case.meta.member
        if member == "path-traversal":
            return legacy.safe_slug("../../etc/passwd")
        if member == "absolute-path":
            return legacy.safe_slug("/etc/shadow")
        if member == "unicode-name":
            return legacy.safe_slug("日本語太郎")
        if member == "case-collision":
            run_identity = legacy.RunIdentity()
            id_a = run_identity.output_id(legacy.AttendeeId.parse("90000001"))
            id_b = run_identity.output_id(legacy.AttendeeId.parse("90000002"))
            stem_a = legacy.attendee_filename_stem("Avery Archer", id_a)
            stem_b = legacy.attendee_filename_stem("AVERY ARCHER", id_b)
            return (
                stem_a.startswith("avery-archer-"),
                stem_b.startswith("avery-archer-"),
                stem_a != stem_b,
            )
        if member == "windows-reserved":
            return legacy.safe_slug("CON")
        if member == "empty-name":
            return legacy.safe_slug("")
        if member == "symlinked-root":
            real_dir = root / "real-output"
            real_dir.mkdir()
            symlink_root = root / "output-symlink"
            symlink_root.symlink_to(real_dir, target_is_directory=True)
            legacy.atomic_write_text(symlink_root / "probe.txt", "hello")
            # The file was published through the symlink, into real_dir -- the CURRENT,
            # un-fixed observation. Slice 2 (target_owner) will reject this before publishing.
            return (real_dir / "probe.txt").read_text(encoding="utf-8-sig")
        if member == "duplicate-display-name":
            run_identity = legacy.RunIdentity()
            id_a = run_identity.output_id(legacy.AttendeeId.parse("90000003"))
            id_b = run_identity.output_id(legacy.AttendeeId.parse("90000004"))
            stem_a = legacy.attendee_filename_stem("Avery Example", id_a)
            stem_b = legacy.attendee_filename_stem("Avery Example", id_b)
            return stem_a != stem_b
        if member == "duplicate-html-filename":
            result_1 = _build_result((), root)
            legacy.write_outputs(
                root, [result_1], generate_html=True, html_name="sub/dir/report.html"
            )
            first_text = (root / "report.html").read_text(encoding="utf-8")
            result_2 = _build_result((_class_row_for_test(),), root)
            legacy.write_outputs(
                root, [result_2], generate_html=True, html_name="../escape/report.html"
            )
            second_text = (root / "report.html").read_text(encoding="utf-8")
            return (
                (root / "sub").exists(),
                (root.parent / "escape").exists(),
                first_text != second_text,  # second write cleanly overwrote the first
            )
        raise AssertionError(f"unknown ART-NAME member: {member}")

    # -- formula ------------------------------------------------------------------------------

    def _ctx_formula(self, case: ArtifactCase, root: Path) -> object:
        import scout_schedule_cli as legacy

        value = str(case.input_rows[0]["scout_name"])
        row = legacy.ClassRecord(
            scout_name=value,
            attendee_id="90000001",
            class_number="26MB1",
            class_p4_id="2000001",
            class_name="Chess",
            days="MoTuWeTh",
            period_name="A Block",
            start_time="09:00 AM",
            start_time_24h="09:00:00",
            location="Pavilion",
            has_requirements=True,
            class_completed=False,
            raw_class_name="Chess",
        )
        legacy.write_csv(root / "classes.csv", [row], list(legacy.ClassRecord.__dataclass_fields__))
        raw_bytes = (root / "classes.csv").read_bytes()
        text = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        # PRESERVE: no formula-injection defense exists -- the raw prefix survives unescaped.
        return list(reader)[0]["scout_name"]

    # -- atomic_fail --------------------------------------------------------------------------

    def _ctx_atomic_fail(self, case: ArtifactCase, root: Path) -> object:
        import scout_schedule_cli as legacy

        member = case.meta.member
        target = root / "out.txt"

        if member == "before-render":
            target.write_text("prior-content", encoding="utf-8-sig")
            with patch.object(Path, "open", side_effect=OSError("boom")), pytest.raises(OSError):
                legacy.atomic_write_text(target, "new-content")
            return (target.read_text(encoding="utf-8-sig"), len(list(root.glob("*.tmp"))))

        if member == "during-temp-write":
            target.write_text("prior-content", encoding="utf-8-sig")
            with patch.object(os, "fsync", side_effect=OSError("boom")), pytest.raises(OSError):
                legacy.atomic_write_text(target, "new-content")
            return (target.read_text(encoding="utf-8-sig"), len(list(root.glob("*.tmp"))))

        if member == "before-atomic-replace":
            target.write_text("prior-content", encoding="utf-8-sig")
            with patch.object(os, "replace", side_effect=OSError("boom")), pytest.raises(OSError):
                legacy.atomic_write_text(target, "new-content")
            return (target.read_text(encoding="utf-8-sig"), len(list(root.glob("*.tmp"))))

        if member == "after-atomic-replace":
            result_1 = _build_result((_class_row_for_test(),), root)
            call_count = {"n": 0}
            real_replace = os.replace

            def flaky_replace(src, dst):
                call_count["n"] += 1
                if call_count["n"] == 2:
                    raise OSError("boom")
                return real_replace(src, dst)

            with patch.object(os, "replace", side_effect=flaky_replace), pytest.raises(OSError):
                legacy.write_outputs(root, [result_1], generate_html=False)
            exists = (root / "scouts.json").exists()
            payload = json.loads((root / "scouts.json").read_text(encoding="utf-8"))
            return (exists, len(payload))

        if member == "during-cleanup":
            with (
                patch.object(Path, "unlink", side_effect=OSError("cleanup-boom")),
                pytest.raises(OSError, match="cleanup-boom"),
            ):
                legacy.atomic_write_text(target, "new-content")
            # The publish itself succeeded even though cleanup raised afterwards.
            return target.read_text(encoding="utf-8-sig")

        if member == "partial-multi-file":
            result_1 = _build_result((_class_row_for_test(), _requirement_row_for_test()), root)
            call_count = {"n": 0}
            real_replace = os.replace

            def flaky_replace(src, dst):
                call_count["n"] += 1
                if call_count["n"] == 3:
                    raise OSError("boom")
                return real_replace(src, dst)

            with patch.object(os, "replace", side_effect=flaky_replace), pytest.raises(OSError):
                legacy.write_outputs(root, [result_1], generate_html=True)
            return (
                (root / "scouts.json").exists(),
                (root / "classes.csv").exists(),
                (root / "requirements.csv").exists(),
                (root / "errors.csv").exists(),
                (root / "report.html").exists(),
                (root / "summary.json").exists(),
            )

        raise AssertionError(f"unknown ART-FAIL member: {member}")


def _class_row_for_test() -> dict:
    return {
        "scout_name": "Avery Example",
        "attendee_id": "90000001",
        "class_number": "26MB1",
        "class_p4_id": "2000001",
        "class_name": "Chess",
        "days": "MoTuWeTh",
        "period_name": "A Block",
        "start_time": "09:00 AM",
        "start_time_24h": "09:00:00",
        "location": "Pavilion",
        "has_requirements": True,
        "class_completed": False,
        "raw_class_name": "Chess",
    }


def _requirement_row_for_test() -> dict:
    return {
        "scout_name": "Avery Example",
        "attendee_id": "90000001",
        "class_number": "26MB1",
        "class_p4_id": "2000001",
        "merit_badge_name": "Chess",
        "requirement_id": "r1",
        "requirement_type_id": "1",
        "requirement_number": "#1a",
        "description": "Show work.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }


@pytest.mark.parametrize(("case", "context_id"), execution_params(ARTIFACT_CASES))
def test_artifact_execution(case: ArtifactCase, context_id: str, tmp_path: Path) -> None:
    observed = LegacyArtifactRunner(context_id).run(case, root=tmp_path)
    assert observed == case.expected_by_context[context_id]


def test_artifact_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.artifact_cases import ALL_ARTIFACT_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    art_axes = [axis for axis in AXES if axis.domain is Domain.ARTIFACT]
    art_boundaries = [b for b in BOUNDARIES if b.domain is Domain.ARTIFACT]

    errors = validate_registry(ALL_ARTIFACT_METADATA, art_axes, art_boundaries, [], list(POLICIES))
    assert errors == ()
