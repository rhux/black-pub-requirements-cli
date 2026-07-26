from __future__ import annotations

from scoutmb.core.inference.status import calculate_statuses
from scoutmb.core.inference.tree import build_group_tree


def _statuses(numbers, type_ids, completed, descriptions=None):
    tree = build_group_tree(numbers, type_ids)
    return calculate_statuses(
        tree=tree,
        completed=completed,
        descriptions=descriptions or ("",) * len(numbers),
    )


def test_leaf_incomplete_has_no_rollup_keys() -> None:
    result = _statuses(("#1",), ("1",), (False,))
    assert result[0].status == "incomplete"
    assert result[0].reason == "Not marked complete by ScoutingEvent."
    assert result[0].total_subrequirements is None, "presence of this key gates actionability"


def test_api_complete_wins_over_children() -> None:
    result = _statuses(("#2", "#2a"), ("1", "1"), (True, False))
    assert result[0].status == "complete"
    assert result[0].reason == "Marked complete by ScoutingEvent."


def test_all_children_complete_rolls_up() -> None:
    result = _statuses(("#3", "#3a"), ("1", "1"), (False, True))
    assert result[0].status == "complete"
    assert result[0].reason == "All 1 subrequirements are complete."
    assert result[0].completed_subrequirements == 1
    assert result[0].total_subrequirements == 1


def test_choice_threshold_yields_complete_check() -> None:
    result = _statuses(
        ("#4", "#4a", "#4b"),
        ("1", "1", "1"),
        (False, True, False),
        descriptions=("Do ONE of the following.", "", ""),
    )
    assert result[0].status == "complete_check"
    assert "meets the stated choice of 1" in result[0].reason


def test_complete_check_propagates_to_a_fully_satisfied_parent() -> None:
    # #5a itself must land on complete_check (not plain complete) for propagation to be
    # observable at #5, so #5a needs its own choice-threshold ambiguity: 1 of 2 children
    # satisfied against a stated choice of 1. A directly-API-completed leaf would instead
    # resolve #5a to a flat "complete", never exercising the propagation branch on #5.
    result = _statuses(
        ("#5", "#5a", "#5a1", "#5a2"),
        ("1", "1", "1", "1"),
        (False, False, True, False),
        descriptions=("", "Do ONE of the following.", "", ""),
    )
    assert result[1].status == "complete_check"
    assert result[0].status == "complete_check"
    assert "inferred from a choice requirement" in result[0].reason
