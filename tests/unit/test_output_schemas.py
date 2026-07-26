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
def test_flag_coercion_matches_legacy_truthy(raw: object, expected: bool) -> None:
    """bool("0") is True; truthy("0") is False. The legacy uses truthy()."""
    import scout_schedule_cli as legacy

    from scoutmb.core.output_schemas import _flag

    assert _flag(raw) is expected is legacy.truthy(raw)


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


def test_requirement_to_row_shareable_true_raises_not_implemented() -> None:
    """shareable=True is not yet wired (Task 23 does the real field-dropping); until then it
    must raise loudly rather than silently return the full operational row."""
    with pytest.raises(NotImplementedError):
        requirement_to_row(_dto("3b"), shareable=True)


def test_requirement_to_row_shareable_false_still_works() -> None:
    row = requirement_to_row(_dto("3b"), shareable=False)
    assert row["requirement_number"] == "3b"


def test_class_to_row_shareable_true_raises_not_implemented() -> None:
    """Mirror of the RequirementRecord guard: shareable=True must fail loudly, not silently."""
    with pytest.raises(NotImplementedError):
        class_to_row(_class_dto(), shareable=True)


def test_class_to_row_shareable_false_still_works() -> None:
    row = class_to_row(_class_dto(), shareable=False)
    assert row["class_name"] == "Chess"


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
