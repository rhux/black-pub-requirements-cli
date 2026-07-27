"""The one fixture both goldens are generated from.

A golden built from clean single-attendee data proves almost nothing about this refactor. Two
same-named attendees are the load-bearing case: keying anything on display name collapses
them, which is the exact corruption D3 exists to prevent.
"""

from __future__ import annotations

from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult


def _requirement(
    scout: str, attendee: str, number: str, *, complete: bool = False
) -> RequirementRecord:
    return RequirementRecord(
        scout_name=scout,
        attendee_id=attendee,
        class_number="26MB1",
        class_p4_id="2000001",
        merit_badge_name="Chess",
        requirement_id=f"r-{number}",
        requirement_type_id="1",
        requirement_number=number,
        description=f"Requirement {number} description.",
        completed_requirement=complete,
        completed_class=False,
        requirement_on_event=True,
        present_days="MoTuWeTh",
    )


def _class(scout: str, attendee: str) -> ClassRecord:
    return ClassRecord(
        scout_name=scout,
        attendee_id=attendee,
        class_number="26MB1",
        class_p4_id="2000001",
        class_name="Chess",
        days="MoTuWeTh",
        period_name="Period 1",
        start_time="9:00 AM",
        start_time_24h="09:00",
        location="Pavilion",
        has_requirements=True,
        class_completed=False,
        raw_class_name="MoTuWeTh - Chess",
    )


# Sentinels go ONLY in the fields the shareable projection actually removes or never carries.
# An earlier draft also seeded `description`, `requirement_id`, and an error string -- but the
# shareable schema PRESERVES those fields verbatim, and the V1->V2 rule requires every
# non-identity value to be unchanged. So "no sentinel reaches report.html" would have been
# unsatisfiable without violating the schema: the test and the contract contradicted.
#
# In 2a the record shape holds exactly two forbidden values: the upstream attendee ID and the
# QR bearer token. Session material and raw payload fragments live in gateway state that does
# not exist until 2b; their sentinels belong to 2b's gateway fixture, not here.
SENTINEL_UPSTREAM_ID = "zzsentinel-upstream-id-should-never-leak"
SENTINEL_QR_TOKEN = "zzsentinel-qr-bearer-token-should-never-leak"


def sentinel_results() -> list[ScoutResult]:
    """The golden fixture plus one attendee carrying a sentinel in each forbidden field.

    A privacy assertion is only meaningful if the value it forbids is actually present
    upstream: asserting the absence of a string the fixture never contained is a test that
    cannot fail.
    """
    name = "Sentinel Subject"
    return [
        ScoutResult(
            name=name,
            qr_url=f"https://scoutingevent.com/mobile/checkin?t={SENTINEL_QR_TOKEN}",
            attendee_id=SENTINEL_UPSTREAM_ID,
            classes=(_class(name, SENTINEL_UPSTREAM_ID),),
            requirements=(_requirement(name, SENTINEL_UPSTREAM_ID, "1"),),
            errors=("requirement fetch failed",),
        ),
        *golden_results(),
    ]


def golden_results() -> list[ScoutResult]:
    same_name = "Jordan Sample"
    return [
        # Two attendees SHARING a display name with different upstream IDs.
        ScoutResult(
            name=same_name,
            qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_A",
            attendee_id="90000001",
            classes=(_class(same_name, "90000001"),),
            requirements=(
                _requirement(same_name, "90000001", "1", complete=True),
                _requirement(same_name, "90000001", "2"),
            ),
        ),
        ScoutResult(
            name=same_name,
            qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_B",
            attendee_id="90000002",
            classes=(_class(same_name, "90000002"),),
            requirements=(_requirement(same_name, "90000002", "1"),),
        ),
        # Zero classes, zero requirements.
        ScoutResult(
            name="Riley Quiet",
            qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_C",
            attendee_id="90000003",
        ),
        # Partial failure: data acquired AND an error recorded.
        ScoutResult(
            name="Casey Partial",
            qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_D",
            attendee_id="90000004",
            classes=(_class("Casey Partial", "90000004"),),
            requirements=(_requirement("Casey Partial", "90000004", "3"),),
            errors=("requirement fetch failed for class 2000002",),
        ),
        # Pre-identity failure: process_scout builds the result BEFORE reading attendee_id,
        # so a navigation failure returns one with attendee_id == "". output_id must be null.
        ScoutResult(
            name="Morgan Unreached",
            qr_url="https://scoutingevent.com/mobile/checkin?t=TOKEN_E",
            attendee_id="",
            errors=("Timeout 45000ms exceeded.",),
        ),
    ]
