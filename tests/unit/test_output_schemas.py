from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES

from scoutmb.core.models import RequirementRecord
from scoutmb.core.output_schemas import requirement_from_mapping, requirement_to_row


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
