from __future__ import annotations

from scoutmb.core.inference.missing import is_not_used, select_actionable


def _row(**overrides):
    row = {
        "attendee_id": "90000001",
        "class_p4_id": "2000001",
        "requirement_number": "1",
        "requirement_type_id": "1",
        "description": "Do the thing.",
        "calculated_status": "incomplete",
        "parent_requirement_number": None,
    }
    row.update(overrides)
    return row


def _key(row):
    return str(row.get("attendee_id") or "")


def test_not_used_rows_are_never_selected() -> None:
    rows = [_row(description="This requirement is (not used) here.")]
    assert select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str) == {}


def test_type_3_rows_are_never_selected() -> None:
    rows = [_row(requirement_type_id="3")]
    assert select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str) == {}


def test_rows_with_children_are_not_actionable_leaves() -> None:
    rows = [_row(total_subrequirements=2, completed_subrequirements=1)]
    assert select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str) == {}


def test_is_not_used_is_case_insensitive() -> None:
    assert is_not_used("Something (NOT USED) here")
    assert not is_not_used("Something used here")
