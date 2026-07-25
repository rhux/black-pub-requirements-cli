from __future__ import annotations

import pytest
import scout_schedule_cli as legacy

from scoutmb.core.identity import AttendeeId, MissingAttendeeId, RunIdentity, safe_slug


@pytest.mark.parametrize(
    "value",
    ["Avery Example", "  Mixed   Case  ", "O'Neil-Smith", "", "!!!", "Ünïcödé Näme"],
)
def test_safe_slug_matches_legacy(value: str) -> None:
    assert safe_slug(value) == legacy.safe_slug(value)


def test_legacy_names_are_the_package_objects() -> None:
    """Re-export, not a copy: a second implementation would drift silently."""
    assert legacy.safe_slug is safe_slug
    assert legacy.AttendeeId is AttendeeId
    assert legacy.RunIdentity is RunIdentity
    assert legacy.MissingAttendeeId is MissingAttendeeId


def test_blank_attendee_id_fails_closed() -> None:
    with pytest.raises(MissingAttendeeId):
        AttendeeId.parse("   ", "Avery Example")


def test_output_id_is_stable_within_a_run_and_distinct_across_attendees() -> None:
    identity = RunIdentity()
    first = identity.output_id(AttendeeId.parse("90000001"))
    again = identity.output_id(AttendeeId.parse("90000001"))
    other = identity.output_id(AttendeeId.parse("90000002"))
    assert first == again
    assert first != other
