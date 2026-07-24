"""Typed matrix execution of the artifact characterization catalog (Task 20).

Each ``ART-*`` case drives the REAL ``scout_schedule_cli`` output writers (never mocked, except
at the exact filesystem seams the ``ART-FAIL-*`` cases name). No test writes outside
``tmp_path`` and none performs real network I/O.
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
        legacy.ClassRecord(**{k: v for k, v in row.items() if k in legacy.ClassRecord.__dataclass_fields__})
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

    def run(self, case: ArtifactCase, *, root: Path) -> None:
        getattr(self, f"_ctx_{self.context_id}")(case, root)

    # -- schema -----------------------------------------------------------------------------

    def _ctx_schema(self, case: ArtifactCase, root: Path) -> None:
        import scout_schedule_cli as legacy

        result = _build_result(case.input_rows, root)
        member = case.meta.member

        if member == "scouts-json":
            legacy.write_outputs(root, [result], generate_html=False)
            payload = json.loads((root / "scouts.json").read_text(encoding="utf-8"))
            assert payload == [
                {
                    "name": "Avery Example",
                    "qr_url": "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
                    "attendee_id": "90000001",
                    "classes": [asdict(c) for c in result.classes],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": [],
                }
            ]
        elif member == "classes-csv":
            legacy.write_outputs(root, [result], generate_html=False)
            text = (root / "classes.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            assert reader.fieldnames == list(legacy.ClassRecord.__dataclass_fields__)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["class_name"] == "Chess"
        elif member == "requirements-csv":
            legacy.write_outputs(root, [result], generate_html=False)
            text = (root / "requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            assert reader.fieldnames == list(legacy.RequirementRecord.__dataclass_fields__)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["requirement_number"] == "#1a"
        elif member == "errors-csv":
            result.errors.append("boom")
            legacy.write_outputs(root, [result], generate_html=False)
            text = (root / "errors.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            assert reader.fieldnames == ["scout_name", "attendee_id", "error"]
            rows = list(reader)
            assert rows == [{"scout_name": "Avery Example", "attendee_id": "90000001", "error": "boom"}]
        elif member == "summary-json":
            legacy.write_outputs(root, [result], generate_html=True)
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            assert set(summary) == {
                "scouts_processed", "scouts_with_errors", "classes", "requirements",
                "generated_at_local", "generated_at_iso", "html_report", "email_report_dir",
            }
            assert summary["scouts_processed"] == 1
            assert summary["classes"] == 1
            assert summary["requirements"] == 1
            assert summary["html_report"] == "report.html"
            assert summary["email_report_dir"] is None
        elif member == "report-data":
            legacy.write_outputs(root, [result], generate_html=True)
            html_text = (root / "report.html").read_text(encoding="utf-8")
            assert "__REPORT_DATA__" not in html_text
            start = html_text.index('<script id="report-data" type="application/json">') + len(
                '<script id="report-data" type="application/json">'
            )
            end = html_text.index("</script>", start)
            payload = json.loads(html_text[start:end])
            assert set(payload) == {
                "generated_at_local", "generated_at_iso", "run_id", "scouts", "classes",
                "requirements", "errors",
            }
            assert len(payload["classes"]) == 1
            assert len(payload["requirements"]) == 1
        elif member == "email-csv":
            nested = [
                {
                    "name": result.name, "attendee_id": result.attendee_id,
                    "classes": [asdict(c) for c in result.classes],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": result.errors,
                }
            ]
            legacy.write_email_reports(root, nested)
            text = (root / "emails" / "missing_requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            assert reader.fieldnames == [
                "scout_name", "attendee_id", "status", "merit_badge_count",
                "missing_requirement_count", "subject", "body_text", "body_html",
            ]
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["status"] == "missing_requirements"
        elif member == "email-text-html":
            nested = [
                {
                    "name": result.name, "attendee_id": result.attendee_id,
                    "classes": [asdict(c) for c in result.classes],
                    "requirements": [asdict(r) for r in result.requirements],
                    "errors": result.errors,
                }
            ]
            legacy.write_email_reports(root, nested)
            emails_dir = root / "emails"
            txt_files = list(emails_dir.glob("*.txt"))
            html_files = list(emails_dir.glob("*.html"))
            assert len(txt_files) == 1
            assert len(html_files) == 1
            assert txt_files[0].read_bytes().decode("utf-8").startswith("Hi Avery Example,")
            assert "<!doctype html>" in html_files[0].read_bytes().decode("utf-8")
        else:
            raise AssertionError(f"unknown ART-SCHEMA member: {member}")

    # -- html -------------------------------------------------------------------------------

    def _ctx_html(self, case: ArtifactCase, root: Path) -> None:
        import scout_schedule_cli as legacy

        row = case.input_rows[0]
        description = str(row["description"])
        annotated = legacy.annotate_requirement_statuses([dict(row)])
        embedded = legacy.json_for_html({"requirements": annotated})

        member = case.meta.member
        if member in {"xss-sentinel", "script-close-tag", "angle-amp"}:
            assert "</script>" not in embedded
            if "<" in description:
                assert "\\u003c" in embedded
            if ">" in description:
                assert "\\u003e" in embedded
            if "&" in description:
                assert "\\u0026" in embedded
        if member == "line-para-separators":
            assert " " not in embedded
            assert " " not in embedded
            assert "\\u2028" in embedded
            assert "\\u2029" in embedded
        if member == "non-ascii-unicode":
            assert "Café" in embedded  # ensure_ascii=False keeps non-ASCII literal
            assert "徽章" in embedded

        decoded = json.loads(embedded)
        assert decoded["requirements"][0]["description"] == description

    # -- email ------------------------------------------------------------------------------

    def _ctx_email(self, case: ArtifactCase, root: Path) -> None:
        import scout_schedule_cli as legacy

        member = case.meta.member
        if member == "missing-requirements":
            result = _build_result(case.input_rows, root)
            nested = [
                {
                    "name": result.name, "attendee_id": result.attendee_id, "classes": [],
                    "requirements": [asdict(r) for r in result.requirements], "errors": [],
                }
            ]
            legacy.write_email_reports(root, nested)
            emails_dir = root / "emails"
            assert len(list(emails_dir.glob("*.txt"))) == 1
            assert len(list(emails_dir.glob("*.html"))) == 1
        elif member == "all-complete":
            result = _build_result(case.input_rows, root)
            nested = [
                {
                    "name": result.name, "attendee_id": result.attendee_id, "classes": [],
                    "requirements": [asdict(r) for r in result.requirements], "errors": [],
                }
            ]
            legacy.write_email_reports(root, nested)
            emails_dir = root / "emails"
            assert list(emails_dir.glob("*.txt")) == []
            assert list(emails_dir.glob("*.html")) == []
            text = (emails_dir / "missing_requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            assert list(reader)[0]["status"] == "all_complete"
        elif member == "no-data":
            nested = [
                {
                    "name": "Avery Example", "attendee_id": "90000001", "classes": [],
                    "requirements": [], "errors": ["something failed"],
                }
            ]
            legacy.write_email_reports(root, nested)
            text = (root / "emails" / "missing_requirements.csv").read_text(encoding="utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            assert list(reader)[0]["status"] == "no_data_scraped"
        elif member == "same-name-disambiguation":
            nested = [
                {
                    "name": "Avery Example", "attendee_id": row["attendee_id"], "classes": [],
                    "requirements": [dict(row, requirement_number="#1a")], "errors": [],
                }
                for row in case.input_rows
            ]
            legacy.write_email_reports(root, nested)
            txt_files = sorted(p.name for p in (root / "emails").glob("*.txt"))
            assert len(txt_files) == 2
            assert txt_files[0] != txt_files[1]
        else:
            raise AssertionError(f"unknown ART-EMAIL member: {member}")

    # -- filename ---------------------------------------------------------------------------

    def _ctx_filename(self, case: ArtifactCase, root: Path) -> None:
        import scout_schedule_cli as legacy

        member = case.meta.member
        if member == "path-traversal":
            assert legacy.safe_slug("../../etc/passwd") == "etc-passwd"
        elif member == "absolute-path":
            assert legacy.safe_slug("/etc/shadow") == "etc-shadow"
        elif member == "unicode-name":
            assert legacy.safe_slug("日本語太郎") == "unknown-scout"
        elif member == "case-collision":
            run_identity = legacy.RunIdentity()
            id_a = run_identity.output_id(legacy.AttendeeId.parse("90000001"))
            id_b = run_identity.output_id(legacy.AttendeeId.parse("90000002"))
            stem_a = legacy.attendee_filename_stem("Avery Archer", id_a)
            stem_b = legacy.attendee_filename_stem("AVERY ARCHER", id_b)
            assert stem_a.startswith("avery-archer-")
            assert stem_b.startswith("avery-archer-")
            assert stem_a != stem_b
        elif member == "windows-reserved":
            assert legacy.safe_slug("CON") == "con"
        elif member == "empty-name":
            assert legacy.safe_slug("") == "unknown-scout"
        elif member == "symlinked-root":
            real_dir = root / "real-output"
            real_dir.mkdir()
            symlink_root = root / "output-symlink"
            symlink_root.symlink_to(real_dir, target_is_directory=True)
            legacy.atomic_write_text(symlink_root / "probe.txt", "hello")
            # The file was published through the symlink, into real_dir -- the CURRENT,
            # un-fixed observation. Slice 2 (target_owner) will reject this before publishing.
            assert (real_dir / "probe.txt").read_text(encoding="utf-8-sig") == "hello"
        elif member == "duplicate-display-name":
            run_identity = legacy.RunIdentity()
            id_a = run_identity.output_id(legacy.AttendeeId.parse("90000003"))
            id_b = run_identity.output_id(legacy.AttendeeId.parse("90000004"))
            stem_a = legacy.attendee_filename_stem("Avery Example", id_a)
            stem_b = legacy.attendee_filename_stem("Avery Example", id_b)
            assert stem_a != stem_b
        elif member == "duplicate-html-filename":
            result_1 = _build_result((), root)
            legacy.write_outputs(root, [result_1], generate_html=True, html_name="sub/dir/report.html")
            first_text = (root / "report.html").read_text(encoding="utf-8")
            result_2 = _build_result((_class_row_for_test(),), root)
            legacy.write_outputs(root, [result_2], generate_html=True, html_name="../escape/report.html")
            second_text = (root / "report.html").read_text(encoding="utf-8")
            assert not (root / "sub").exists()
            assert not (root.parent / "escape").exists()
            assert first_text != second_text  # second write cleanly overwrote the first
        else:
            raise AssertionError(f"unknown ART-NAME member: {member}")

    # -- formula ------------------------------------------------------------------------------

    def _ctx_formula(self, case: ArtifactCase, root: Path) -> None:
        import scout_schedule_cli as legacy

        value = str(case.input_rows[0]["scout_name"])
        row = legacy.ClassRecord(
            scout_name=value, attendee_id="90000001", class_number="26MB1",
            class_p4_id="2000001", class_name="Chess", days="MoTuWeTh",
            period_name="A Block", start_time="09:00 AM", start_time_24h="09:00:00",
            location="Pavilion", has_requirements=True, class_completed=False,
            raw_class_name="Chess",
        )
        legacy.write_csv(
            root / "classes.csv", [row], list(legacy.ClassRecord.__dataclass_fields__)
        )
        raw_bytes = (root / "classes.csv").read_bytes()
        text = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        written_value = list(reader)[0]["scout_name"]
        # PRESERVE: no formula-injection defense exists -- the raw prefix survives unescaped.
        assert written_value == value

    # -- atomic_fail --------------------------------------------------------------------------

    def _ctx_atomic_fail(self, case: ArtifactCase, root: Path) -> None:
        import scout_schedule_cli as legacy

        member = case.meta.member
        target = root / "out.txt"

        if member == "before-render":
            target.write_text("prior-content", encoding="utf-8-sig")
            with patch.object(Path, "open", side_effect=OSError("boom")), pytest.raises(OSError):
                legacy.atomic_write_text(target, "new-content")
            assert target.read_text(encoding="utf-8-sig") == "prior-content"
            assert list(root.glob("*.tmp")) == []

        elif member == "during-temp-write":
            target.write_text("prior-content", encoding="utf-8-sig")
            with patch.object(os, "fsync", side_effect=OSError("boom")), pytest.raises(OSError):
                legacy.atomic_write_text(target, "new-content")
            assert target.read_text(encoding="utf-8-sig") == "prior-content"
            assert list(root.glob("*.tmp")) == []

        elif member == "before-atomic-replace":
            target.write_text("prior-content", encoding="utf-8-sig")
            with patch.object(os, "replace", side_effect=OSError("boom")), pytest.raises(OSError):
                legacy.atomic_write_text(target, "new-content")
            assert target.read_text(encoding="utf-8-sig") == "prior-content"
            assert list(root.glob("*.tmp")) == []

        elif member == "after-atomic-replace":
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
            assert (root / "scouts.json").exists()
            payload = json.loads((root / "scouts.json").read_text(encoding="utf-8"))
            assert len(payload) == 1

        elif member == "during-cleanup":
            with (
                patch.object(Path, "unlink", side_effect=OSError("cleanup-boom")),
                pytest.raises(OSError, match="cleanup-boom"),
            ):
                legacy.atomic_write_text(target, "new-content")
            # The publish itself succeeded even though cleanup raised afterwards.
            assert target.read_text(encoding="utf-8-sig") == "new-content"

        elif member == "partial-multi-file":
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
            assert (root / "scouts.json").exists()
            assert (root / "classes.csv").exists()
            assert not (root / "requirements.csv").exists()
            assert not (root / "errors.csv").exists()
            assert not (root / "report.html").exists()
            assert not (root / "summary.json").exists()

        else:
            raise AssertionError(f"unknown ART-FAIL member: {member}")


def _class_row_for_test() -> dict:
    return {
        "scout_name": "Avery Example", "attendee_id": "90000001", "class_number": "26MB1",
        "class_p4_id": "2000001", "class_name": "Chess", "days": "MoTuWeTh",
        "period_name": "A Block", "start_time": "09:00 AM", "start_time_24h": "09:00:00",
        "location": "Pavilion", "has_requirements": True, "class_completed": False,
        "raw_class_name": "Chess",
    }


def _requirement_row_for_test() -> dict:
    return {
        "scout_name": "Avery Example", "attendee_id": "90000001", "class_number": "26MB1",
        "class_p4_id": "2000001", "merit_badge_name": "Chess", "requirement_id": "r1",
        "requirement_type_id": "1", "requirement_number": "#1a", "description": "Show work.",
        "completed_requirement": False, "completed_class": False,
        "requirement_on_event": True, "present_days": "MoTuWeTh",
    }


@pytest.mark.parametrize(("case", "context_id"), execution_params(ARTIFACT_CASES))
def test_artifact_execution(case: ArtifactCase, context_id: str, tmp_path: Path) -> None:
    LegacyArtifactRunner(context_id).run(case, root=tmp_path)


def test_artifact_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.artifact_cases import ALL_ARTIFACT_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    art_axes = [axis for axis in AXES if axis.domain is Domain.ARTIFACT]
    art_boundaries = [b for b in BOUNDARIES if b.domain is Domain.ARTIFACT]

    errors = validate_registry(
        ALL_ARTIFACT_METADATA, art_axes, art_boundaries, [], list(POLICIES)
    )
    assert errors == ()
