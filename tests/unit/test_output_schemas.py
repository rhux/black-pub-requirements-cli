from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES

from scoutmb.core.models import ClassRecord, RequirementRecord
from scoutmb.core.output_schemas import (
    class_from_mapping,
    class_to_row,
    requirement_from_mapping,
    requirement_to_row,
)


def _dto(number: str) -> RequirementRecord:
    return RequirementRecord(
        scout_name="Avery Example",
        attendee_id="90000001",
        class_number="26MB1",
        class_p4_id="2000001",
        merit_badge_name="Chess",
        requirement_id="r1",
        requirement_type_id="1",
        requirement_number=number,
        description="Show your work.",
        completed_requirement=False,
        completed_class=False,
        requirement_on_event=True,
        present_days="MoTuWeTh",
    )


def _class_dto(**overrides: object) -> ClassRecord:
    base: dict[str, object] = {
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
        "raw_class_name": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
    }
    base.update(overrides)
    return ClassRecord(**base)  # type: ignore[arg-type]


@given(st.sampled_from(REQUIREMENT_NUMBER_SHAPES))
def test_dto_round_trip(number: str) -> None:
    """from_mapping(to_row(dto)) == dto -- the ONLY direction that can hold.

    The reverse (to_row(from_mapping(mapping)) == mapping) is false by construction:
    from_mapping coerces types, resolves aliases, drops unknown keys and supplies defaults,
    so the original mapping is not recoverable.
    """
    dto = _dto(number)
    assert requirement_from_mapping(requirement_to_row(dto, shareable=False)) == dto


def test_to_row_preserves_declaration_order() -> None:
    from dataclasses import fields

    row = requirement_to_row(_dto("3b"), shareable=False)
    assert list(row) == [f.name for f in fields(RequirementRecord)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("Yes", True),
        ("y", True),
        ("0", False),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
def test_flag_coercion_pins_legacy_truthy_semantics(raw: object, expected: bool) -> None:
    """bool("0") is True; truthy("0") is False. This table was originally proven equal to
    scout_schedule_cli.truthy() (retired in Slice 2b B10.4, along with `truthy` itself, which
    had no package equivalent to compare against) -- the expected values below are that
    once-proven parity, now pinned directly."""
    from scoutmb.core.output_schemas import _flag

    assert _flag(raw) is expected


def test_text_coercion_does_not_strip() -> None:
    """Legacy strips present_days and nothing else; stripping elsewhere is a silent change."""
    from scoutmb.core.output_schemas import requirement_from_mapping

    record = requirement_from_mapping({"merit_badge_name": "  Chess  ", "present_days": "  Mo  "})
    assert record.merit_badge_name == "  Chess  "
    assert record.present_days == "Mo"


def test_serializer_normalizes_tuples_to_lists() -> None:
    """asdict PRESERVES tuples (proven in tests/packaging/test_mechanisms.py), so the
    serializer must normalize or a tuple reaches a CSV cell as its repr."""
    from scoutmb.core.models import ScoutResult
    from scoutmb.core.output_schemas import scout_result_to_row

    row = scout_result_to_row(ScoutResult(name="Avery Example", qr_url="https://x.invalid"))
    assert isinstance(row["classes"], list)
    assert isinstance(row["errors"], list)


def test_scout_result_from_row_reverses_scout_result_to_row() -> None:
    from scoutmb.core.models import ScoutResult
    from scoutmb.core.output_schemas import scout_result_from_row, scout_result_to_row

    original = ScoutResult(
        name="Avery Example",
        qr_url="https://x.invalid",
        attendee_id="A1",
        classes=(
            ClassRecord(
                scout_name="Avery Example",
                attendee_id="A1",
                class_number="101",
                class_p4_id="p4-1",
                class_name="Camping",
                days="Mon",
                period_name="AM",
                start_time="9:00",
                start_time_24h="09:00",
                location="Hall",
                has_requirements=True,
                class_completed=False,
                raw_class_name="Camping (raw)",
            ),
        ),
        requirements=(
            RequirementRecord(
                scout_name="Avery Example",
                attendee_id="A1",
                class_number="101",
                class_p4_id="p4-1",
                merit_badge_name="Camping",
                requirement_id="r1",
                requirement_type_id="t1",
                requirement_number="1a",
                description="Do a thing",
                completed_requirement=True,
                completed_class=False,
                requirement_on_event=True,
                present_days="Mon,Tue",
            ),
        ),
        errors=("Camping: requirement request failed: timeout",),
    )
    row = scout_result_to_row(original)
    assert scout_result_from_row(row) == original


def test_requirement_to_row_shareable_true_substitutes_output_id_in_place() -> None:
    """attendee_id is replaced BY output_id at the same index -- a deletion plus an insertion,
    never a reordering (Task 23)."""
    from dataclasses import fields

    row = requirement_to_row(_dto("3b"), shareable=True, output_id="the-output-id")
    assert "attendee_id" not in row
    assert row["output_id"] == "the-output-id"
    expected_keys = [
        "output_id" if f.name == "attendee_id" else f.name for f in fields(RequirementRecord)
    ]
    assert list(row) == expected_keys


def test_requirement_to_row_shareable_true_defaults_output_id_to_none() -> None:
    """An attempt that failed before identity resolution carries output_id: None, never an
    omitted key and never a placeholder string."""
    row = requirement_to_row(_dto("3b"), shareable=True)
    assert row["output_id"] is None


def test_requirement_to_row_shareable_false_still_works() -> None:
    row = requirement_to_row(_dto("3b"), shareable=False)
    assert row["requirement_number"] == "3b"
    assert row["attendee_id"] == "90000001"


def test_class_to_row_shareable_true_substitutes_output_id_in_place() -> None:
    """Mirror of the RequirementRecord case: attendee_id is replaced by output_id in place."""
    from dataclasses import fields

    row = class_to_row(_class_dto(), shareable=True, output_id="the-output-id")
    assert "attendee_id" not in row
    assert row["output_id"] == "the-output-id"
    expected_keys = [
        "output_id" if f.name == "attendee_id" else f.name for f in fields(ClassRecord)
    ]
    assert list(row) == expected_keys


def test_class_to_row_shareable_true_defaults_output_id_to_none() -> None:
    row = class_to_row(_class_dto(), shareable=True)
    assert row["output_id"] is None


def test_class_to_row_shareable_false_still_works() -> None:
    row = class_to_row(_class_dto(), shareable=False)
    assert row["class_name"] == "Chess"
    assert row["attendee_id"] == "90000001"


def test_class_dto_round_trip() -> None:
    """Mirror of test_dto_round_trip for ClassRecord: from_mapping(to_row(dto)) == dto."""
    dto = _class_dto()
    assert class_from_mapping(class_to_row(dto, shareable=False)) == dto


def test_class_to_row_preserves_declaration_order() -> None:
    """Mirror of test_to_row_preserves_declaration_order for ClassRecord."""
    from dataclasses import fields

    row = class_to_row(_class_dto(), shareable=False)
    assert list(row) == [f.name for f in fields(ClassRecord)]


def test_class_from_mapping_does_not_strip() -> None:
    """Mirror of test_text_coercion_does_not_strip: ClassRecord has no present_days-equivalent
    stripped field, so every text field must survive untouched."""
    record = class_from_mapping({"class_name": "  Chess  ", "location": "  Pavilion  "})
    assert record.class_name == "  Chess  "
    assert record.location == "  Pavilion  "
