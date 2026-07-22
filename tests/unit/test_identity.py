import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import AttendeeId, MissingAttendeeId, RunIdentity  # noqa: E402


def test_blank_attendee_id_fails_closed():
    with pytest.raises(MissingAttendeeId):
        AttendeeId.parse("   ")


def test_valid_attendee_id_round_trips():
    assert AttendeeId.parse("90000001").value == "90000001"


def test_output_id_is_uuid4_stable_within_run_and_distinct():
    run = RunIdentity()
    a = run.output_id(AttendeeId.parse("90000001"))
    b = run.output_id(AttendeeId.parse("90000002"))
    assert uuid.UUID(a).version == 4
    assert a == run.output_id(AttendeeId.parse("90000001"))  # stable within run
    assert a != b
    assert "90000001" not in a


def test_two_runs_are_unlinkable():
    a = RunIdentity().output_id(AttendeeId.parse("90000001"))
    b = RunIdentity().output_id(AttendeeId.parse("90000001"))
    assert a != b
