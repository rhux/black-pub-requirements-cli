"""The package records must be field-for-field identical to the legacy ones, in order.
ART-SCHEMA-002/003 pin the CSV header to __dataclass_fields__ order, so a reorder here is a
silent breaking change to a shipped artifact."""

from __future__ import annotations

from dataclasses import asdict, fields

import scout_schedule_cli as legacy

from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutInput, ScoutResult


def test_class_record_fields_match_legacy_in_order() -> None:
    assert [(f.name, f.type) for f in fields(ClassRecord)] == [
        (f.name, f.type) for f in fields(legacy.ClassRecord)
    ]


def test_requirement_record_fields_match_legacy_in_order() -> None:
    assert [(f.name, f.type) for f in fields(RequirementRecord)] == [
        (f.name, f.type) for f in fields(legacy.RequirementRecord)
    ]


def test_scout_input_fields_match_legacy_in_order() -> None:
    assert [(f.name, f.type) for f in fields(ScoutInput)] == [
        (f.name, f.type) for f in fields(legacy.ScoutInput)
    ]


def test_scout_input_stays_mutable() -> None:
    scout_input = ScoutInput(name="Avery Example", url="https://example.invalid/x")
    scout_input.name = "Changed Name"
    scout_input.url = "https://example.invalid/y"
    scout_input.registrant_type = "Scout"
    assert scout_input.name == "Changed Name"
    assert scout_input.url == "https://example.invalid/y"
    assert scout_input.registrant_type == "Scout"


def test_scout_result_collections_are_tuples() -> None:
    result = ScoutResult(name="Avery Example", qr_url="https://example.invalid/x")
    assert result.classes == ()
    assert result.requirements == ()
    assert result.errors == ()


def test_asdict_preserves_declaration_order() -> None:
    record = RequirementRecord(
        scout_name="Avery Example",
        attendee_id="90000001",
        class_number="26MB1",
        class_p4_id="2000001",
        merit_badge_name="Chess",
        requirement_id="r1",
        requirement_type_id="1",
        requirement_number="3b",
        description="Show your work.",
        completed_requirement=False,
        completed_class=False,
        requirement_on_event=True,
        present_days="MoTuWeTh",
    )
    assert list(asdict(record)) == [f.name for f in fields(legacy.RequirementRecord)]
