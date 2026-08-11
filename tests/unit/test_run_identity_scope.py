"""One run, one identity map.

Before this task write_email_reports built its own RunIdentity, so an attendee's email
filename UUID had no relationship to the UUID used for its raw/ files in the same run.
"""

from __future__ import annotations

from pathlib import Path

from scoutmb.core.identity import AttendeeId, RunIdentity, attendee_filename_stem
from scoutmb.interfaces.cli.composition import build_reporting_service


def _nested(attendee_id: str, scout_name: str) -> list[dict[str, object]]:
    return [
        {
            "name": scout_name,
            "attendee_id": attendee_id,
            "classes": [],
            "requirements": [
                {
                    "scout_name": scout_name,
                    "attendee_id": attendee_id,
                    "class_number": "26MB1",
                    "class_p4_id": "2000001",
                    "merit_badge_name": "Chess",
                    "requirement_id": "r1",
                    "requirement_type_id": "1",
                    "requirement_number": "3b",
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


def test_email_filenames_use_the_supplied_run_identity(tmp_path: Path) -> None:
    identity = RunIdentity()
    expected = identity.output_id(AttendeeId.parse("90000001"))

    build_reporting_service()._write_email_reports(
        tmp_path, _nested("90000001", "Avery Example"), run_identity=identity
    )

    stems = {p.stem for p in (tmp_path / "emails").glob("*.txt")}
    assert stems == {attendee_filename_stem("Avery Example", expected)}


def test_write_email_reports_creates_no_identity_of_its_own(tmp_path: Path) -> None:
    identity = RunIdentity()
    build_reporting_service()._write_email_reports(
        tmp_path, _nested("90000001", "Avery Example"), run_identity=identity
    )
    # The map now holds exactly the one attendee the writer resolved.
    assert list(identity._by_attendee) == ["90000001"]
