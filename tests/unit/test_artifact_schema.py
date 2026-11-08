"""ART-SCHEMA-001..008: every file ReportingService.publish produces, plus the HTML report-data
payload and the two email artifacts, driven through the REAL writers (never mocked except where
noted) and read back byte-for-byte / row-for-row -- ordered keys/headers, complete rows,
encoding, and newline convention.
"""

from __future__ import annotations

import csv
import json
import re

import pytest

from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult
from scoutmb.interfaces.cli.composition import build_reporting_service

SCOUT_NAME = "Avery Example"
ATTENDEE_ID = "90000001"
CLASS_P4_ID = "2000001"
QR_URL = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X"


def _class_record(**overrides: object) -> ClassRecord:
    fields = {
        "scout_name": SCOUT_NAME,
        "attendee_id": ATTENDEE_ID,
        "class_number": "26MB1",
        "class_p4_id": CLASS_P4_ID,
        "class_name": "Chess",
        "days": "MoTuWeTh",
        "period_name": "A Block",
        "start_time": "09:00 AM",
        "start_time_24h": "09:00:00",
        "location": "Pavilion",
        "has_requirements": True,
        "class_completed": False,
        "raw_class_name": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
    }
    fields.update(overrides)
    return ClassRecord(**fields)


def _requirement_record(**overrides: object) -> RequirementRecord:
    fields = {
        "scout_name": SCOUT_NAME,
        "attendee_id": ATTENDEE_ID,
        "class_number": "26MB1",
        "class_p4_id": CLASS_P4_ID,
        "merit_badge_name": "Chess",
        "requirement_id": "r1",
        "requirement_type_id": "1",
        "requirement_number": "#1a",
        "description": "Show your work.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }
    fields.update(overrides)
    return RequirementRecord(**fields)


def _one_scout_result(**req_overrides: object) -> ScoutResult:
    return ScoutResult(
        name=SCOUT_NAME,
        qr_url=QR_URL,
        attendee_id=ATTENDEE_ID,
        classes=(_class_record(),),
        requirements=(_requirement_record(**req_overrides),),
        errors=(),
    )


@pytest.mark.matrix_case(case_id="ART-SCHEMA-001", context_id="schema", lane="default")
def test_scouts_json_is_a_json_array_of_nested_scout_dicts(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result()],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
    )
    payload = json.loads((out / "scouts.json").read_text(encoding="utf-8"))
    assert payload == [
        {
            "name": SCOUT_NAME,
            "qr_url": QR_URL,
            "attendee_id": ATTENDEE_ID,
            "classes": [
                {
                    "scout_name": SCOUT_NAME,
                    "attendee_id": ATTENDEE_ID,
                    "class_number": "26MB1",
                    "class_p4_id": CLASS_P4_ID,
                    "class_name": "Chess",
                    "days": "MoTuWeTh",
                    "period_name": "A Block",
                    "start_time": "09:00 AM",
                    "start_time_24h": "09:00:00",
                    "location": "Pavilion",
                    "has_requirements": True,
                    "class_completed": False,
                    "raw_class_name": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
                }
            ],
            "requirements": [
                {
                    "scout_name": SCOUT_NAME,
                    "attendee_id": ATTENDEE_ID,
                    "class_number": "26MB1",
                    "class_p4_id": CLASS_P4_ID,
                    "merit_badge_name": "Chess",
                    "requirement_id": "r1",
                    "requirement_type_id": "1",
                    "requirement_number": "#1a",
                    "description": "Show your work.",
                    "completed_requirement": False,
                    "completed_class": False,
                    "requirement_on_event": True,
                    "present_days": "MoTuWeTh",
                }
            ],
            "errors": [],
        }
    ]


@pytest.mark.matrix_case(case_id="ART-SCHEMA-002", context_id="schema", lane="default")
def test_classes_csv_header_and_row(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result()],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
    )
    with (out / "classes.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        raw = fh.read()
        fh.seek(0)
        reader = csv.DictReader(fh)
        fieldnames = tuple(reader.fieldnames)
        rows = list(reader)

    expected_fields = tuple(field.name for field in ClassRecord.__dataclass_fields__.values())
    assert fieldnames == expected_fields
    assert len(rows) == 1
    assert rows[0]["class_name"] == "Chess"
    assert "\r\n" in raw  # csv.DictWriter's default CRLF line terminator, preserved verbatim


@pytest.mark.matrix_case(case_id="ART-SCHEMA-003", context_id="schema", lane="default")
def test_requirements_csv_header_and_row(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result()],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
    )
    with (out / "requirements.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = tuple(reader.fieldnames)
        rows = list(reader)

    expected_fields = tuple(field.name for field in RequirementRecord.__dataclass_fields__.values())
    assert fieldnames == expected_fields
    assert len(rows) == 1
    assert rows[0]["requirement_number"] == "#1a"


@pytest.mark.matrix_case(case_id="ART-SCHEMA-004", context_id="schema", lane="default")
def test_errors_csv_header_and_rows(tmp_path):
    out = tmp_path / "run"
    result = ScoutResult(name=SCOUT_NAME, qr_url=QR_URL, attendee_id=ATTENDEE_ID, errors=("boom",))
    build_reporting_service().publish(
        out,
        [result],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
    )
    with (out / "errors.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    assert fieldnames == ["scout_name", "attendee_id", "error"]
    assert rows == [{"scout_name": SCOUT_NAME, "attendee_id": ATTENDEE_ID, "error": "boom"}]


@pytest.mark.matrix_case(case_id="ART-SCHEMA-005", context_id="schema", lane="default")
def test_summary_json_key_set_and_values(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result()],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=True,
    )
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert frozenset(summary.keys()) == frozenset(
        {
            "scouts_processed",
            "scouts_with_errors",
            "classes",
            "requirements",
            "generated_at_local",
            "generated_at_iso",
            "html_report",
            "email_report_dir",
        }
    )
    assert summary["scouts_processed"] == 1
    assert summary["scouts_with_errors"] == 0
    assert summary["classes"] == 1
    assert summary["requirements"] == 1
    assert summary["html_report"] == "report.html"
    assert summary["email_report_dir"] is None


@pytest.mark.matrix_case(case_id="ART-SCHEMA-006", context_id="schema", lane="default")
def test_report_data_key_set_and_no_placeholder_leftover(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result()],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=True,
    )
    html_text = (out / "report.html").read_text(encoding="utf-8")
    assert "__REPORT_DATA__" not in html_text

    match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>', html_text, re.S
    )
    assert match is not None
    payload = json.loads(match.group(1))

    assert frozenset(payload.keys()) == frozenset(
        {
            "generated_at_local",
            "generated_at_iso",
            "run_id",
            "scouts",
            "classes",
            "requirements",
            "errors",
        }
    )
    assert len(payload["classes"]) == 1
    assert len(payload["requirements"]) == 1


@pytest.mark.matrix_case(case_id="ART-SCHEMA-007", context_id="schema", lane="default")
def test_email_csv_header_and_row(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result(completed_requirement=False)],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
        generate_email_report=True,
    )
    with (out / "emails" / "missing_requirements.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as fh:
        reader = csv.DictReader(fh)
        fieldnames = tuple(reader.fieldnames)
        rows = list(reader)

    assert fieldnames == (
        "scout_name",
        "attendee_id",
        "status",
        "merit_badge_count",
        "missing_requirement_count",
        "subject",
        "body_text",
        "body_html",
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "missing_requirements"


@pytest.mark.matrix_case(case_id="ART-SCHEMA-008", context_id="schema", lane="default")
def test_email_text_and_html_files_written_with_expected_shape(tmp_path):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [_one_scout_result(completed_requirement=False)],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
        generate_email_report=True,
    )
    emails_dir = out / "emails"
    txt_files = list(emails_dir.glob("*.txt"))
    html_files = list(emails_dir.glob("*.html"))
    assert len(txt_files) == 1
    assert len(html_files) == 1

    txt_content = txt_files[0].read_text(encoding="utf-8")
    html_content = html_files[0].read_text(encoding="utf-8")
    assert txt_content.startswith(f"Hi {SCOUT_NAME},")
    assert html_content.lower().startswith("<!doctype html>")

    # No BOM: utf-8 (not utf-8-sig) is what _write_email_reports uses for these two files.
    assert txt_files[0].read_bytes()[:3] != b"\xef\xbb\xbf"
    assert html_files[0].read_bytes()[:3] != b"\xef\xbb\xbf"
