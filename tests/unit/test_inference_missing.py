from __future__ import annotations

from scoutmb.core.inference.missing import (
    group_missing_requirements,
    is_not_used,
    select_actionable,
)


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


# Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b B10.4):
# the ancestor walk's own ``while`` loop -- not exercised by the four tests above, which all use
# a single, parent-less row.


def test_ancestor_walk_stops_at_an_already_complete_parent() -> None:
    rows = [
        _row(requirement_number="1", parent_requirement_number=None, calculated_status="complete"),
        _row(requirement_number="1a", parent_requirement_number="1", calculated_status="incomplete"),
    ]
    selected = select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str)
    assert selected == {1: True}


def test_ancestor_walk_stops_naturally_at_an_already_visited_ancestor() -> None:
    """Two sibling leaves ("1a1", "1a2") share the same incomplete parent ("1a"). The first
    leaf's walk adds "1a" to ``selected`` and stops there (no further parent). The second leaf's
    walk reaches that SAME already-selected "1a" -- the ``while`` loop's own condition
    (``current not in selected``) goes false with no explicit ``break``, exiting back to the
    outer ``for`` loop instead."""
    rows = [
        _row(
            requirement_number="1a",
            parent_requirement_number=None,
            calculated_status="incomplete",
            total_subrequirements=2,
            completed_subrequirements=0,
        ),
        _row(requirement_number="1a1", parent_requirement_number="1a", calculated_status="incomplete"),
        _row(requirement_number="1a2", parent_requirement_number="1a", calculated_status="incomplete"),
    ]
    selected = select_actionable(rows, attendee_key_of=_key, cleaned_description_of=str)
    assert selected == {0: False, 1: True, 2: True}


def test_group_missing_requirements_skips_a_not_used_ancestor() -> None:
    """The ancestor walk itself selects a NOT-USED ancestor (it only checks calculated_status,
    not is_not_used) -- it is group_missing_requirements' own output loop that must exclude it
    from the final grouping."""
    rows = [
        _row(
            requirement_number="2",
            parent_requirement_number=None,
            calculated_status="incomplete",
            description="(Not Used)",
            merit_badge_name="Chess",
            scout_name="Avery Example",
        ),
        _row(
            requirement_number="2a",
            parent_requirement_number="2",
            calculated_status="incomplete",
            merit_badge_name="Chess",
            scout_name="Avery Example",
        ),
    ]
    grouped = group_missing_requirements(rows, attendee_key_of=_key, clean_description=str)
    entries = grouped["90000001"]["badges"]["Chess"]
    numbers = {entry["requirement_number"] for entry in entries}
    assert numbers == {"2a"}
