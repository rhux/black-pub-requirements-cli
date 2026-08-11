"""ART-EMAIL-001..003: ReportingService._write_email_reports' per-scout status/branching.
ART-EMAIL-004 (same-name-disambiguation) is already covered by
tests/unit/test_output_filenames.py::test_email_reports_do_not_collide_for_same_named_attendees.
"""

from __future__ import annotations

import csv

import pytest

from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import RequirementRecord, ScoutResult
from scoutmb.interfaces.cli.composition import build_reporting_service

_SCOUT_NAME = "Avery Example"
_ATTENDEE_ID = "90000001"


def _requirement(*, completed: bool) -> RequirementRecord:
    return RequirementRecord(
        scout_name=_SCOUT_NAME,
        attendee_id=_ATTENDEE_ID,
        class_number="26MB1",
        class_p4_id="2000001",
        merit_badge_name="Chess",
        requirement_id="r1",
        requirement_type_id="1",
        requirement_number="#1a",
        description="Show your work.",
        completed_requirement=completed,
        completed_class=False,
        requirement_on_event=True,
        present_days="MoTuWeTh",
    )


def _publish_and_read(tmp_path, result: ScoutResult):
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [result],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=False,
        generate_email_report=True,
    )
    emails_dir = out / "emails"
    txt_files = list(emails_dir.glob("*.txt"))
    html_files = list(emails_dir.glob("*.html"))
    with (emails_dir / "missing_requirements.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as fh:
        rows = list(csv.DictReader(fh))
    return txt_files, html_files, rows


@pytest.mark.matrix_case(case_id="ART-EMAIL-001", context_id="email", lane="default")
def test_missing_requirements_status_writes_txt_and_html(tmp_path):
    """A scout with one incomplete actionable leaf gets status 'missing_requirements' and BOTH
    a .txt and .html file are written under emails/."""
    result = ScoutResult(
        name=_SCOUT_NAME,
        qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id=_ATTENDEE_ID,
        classes=(),
        requirements=(_requirement(completed=False),),
        errors=(),
    )
    txt_files, html_files, rows = _publish_and_read(tmp_path, result)
    assert len(txt_files) == 1
    assert len(html_files) == 1
    assert rows[0]["status"] == "missing_requirements"


@pytest.mark.matrix_case(case_id="ART-EMAIL-002", context_id="email", lane="default")
def test_all_requirements_complete_writes_no_files(tmp_path):
    """A scout whose only requirement is completed gets status 'all_complete' and NO .txt/.html
    files are written (missing_count == 0 skips the write)."""
    result = ScoutResult(
        name=_SCOUT_NAME,
        qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id=_ATTENDEE_ID,
        classes=(),
        requirements=(_requirement(completed=True),),
        errors=(),
    )
    txt_files, html_files, rows = _publish_and_read(tmp_path, result)
    assert txt_files == []
    assert html_files == []
    assert rows[0]["status"] == "all_complete"


@pytest.mark.matrix_case(case_id="ART-EMAIL-003", context_id="email", lane="default")
def test_no_requirements_but_recorded_error_is_no_data_scraped(tmp_path):
    """A scout with no requirements at all but a recorded error gets status 'no_data_scraped'
    (the 'elif not requirements and errors' branch), not 'all_complete'."""
    result = ScoutResult(
        name=_SCOUT_NAME,
        qr_url="https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_X",
        attendee_id=_ATTENDEE_ID,
        classes=(),
        requirements=(),
        errors=("Schedule API returned failure",),
    )
    txt_files, html_files, rows = _publish_and_read(tmp_path, result)
    assert txt_files == []
    assert html_files == []
    assert rows[0]["status"] == "no_data_scraped"
