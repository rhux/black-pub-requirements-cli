from __future__ import annotations

import pytest
import scout_schedule_cli as legacy

from scoutmb.core.identity import AttendeeId, MissingAttendeeId, RunIdentity, safe_slug


@pytest.mark.parametrize(
    "value",
    ["Avery Example", "  Mixed   Case  ", "O'Neil-Smith", "", "!!!", "Ünïcödé Näme"],
)
def test_safe_slug_matches_legacy(value: str) -> None:
    """`legacy.safe_slug is safe_slug` (see test below), so this only proves the re-export
    is still wired up, not that the slugging logic is correct — that's
    `test_safe_slug_hardcoded_expected_values` below."""
    assert safe_slug(value) == legacy.safe_slug(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Avery Example", "avery-example"),
        ("  Mixed   Case  ", "mixed-case"),
        ("O'Neil-Smith", "o-neil-smith"),
        ("", "unknown-scout"),
        ("!!!", "unknown-scout"),
        ("Ünïcödé Näme", "n-c-d-n-me"),
    ],
)
def test_safe_slug_hardcoded_expected_values(value: str, expected: str) -> None:
    """Independent regression coverage: hardcoded expected outputs verified by hand-tracing
    `safe_slug` (lowercase; non-alphanumeric runs collapsed to a single hyphen; leading/
    trailing hyphens stripped; empty result falls back to "unknown-scout"), not derived from
    or compared against the legacy module."""
    assert safe_slug(value) == expected


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
