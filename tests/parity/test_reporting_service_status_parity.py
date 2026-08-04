"""Differential test for the nested/choice-count/prereq/blank-identity glue that
scout_schedule_cli.annotate_requirement_statuses/render_email_text and
scoutmb.features.reporting.service._annotate_requirement_statuses/_render_email_text each
reimplement independently (service.py cannot import back from the legacy script -- see its
module docstring).

Both copies call the SAME shared core (build_group_tree/calculate_statuses/
group_missing_requirements), so the nested/choice-count algorithm itself is not at risk here.
What IS at risk, and untested until this file, is the surrounding glue: how each copy builds
the tree, threads parent_requirement_number, decides which rollup fields to attach, and renders
the is_prereq suffix. tests/goldens/fixture.py -- the only fixture exercising the package
copy before this file -- is entirely flat (no nested parent/child rows, no choice-count
wording, no prerequisite-flagged row, no fully-identity-blank row); see the EXC-PKG-REPORTING-*
entries in tests/matrix/boundaries.py for the exact lines this gap left uncovered.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import scout_schedule_cli as legacy

from scoutmb.features.reporting import service as reporting_service

# --- Part 1 fixture -----------------------------------------------------------------------
#
# Row "3": a choice-requirement parent ("Do ONE of the following:"), not itself marked
# complete by the API.
# Row "3a"/"3b": its children, one complete one not -- 1 of 2 satisfied meets the stated
# choice of 1, so "3" should roll up to "complete_check" (see
# scoutmb.core.inference.status.calculate_statuses: satisfied_count >= choice_count and
# satisfied_count != total_count -> "complete_check").
# Row "4": a standalone leaf carrying "(pre-req)" in its description, which
# group_missing_requirements/select_actionable reads to set is_prereq=True.
# Row "5": a different scout, same merit badge area, but with BOTH attendee_id and output_id
# blank -- exercises _attendee_key_for's name-only fallback (service.py:57-63,
# scout_schedule_cli.py's equivalent). Distinct scout_name/class_p4_id from rows 1-4 so it
# can't collide into their group.

_CHOICE_SCOUT = "Alex Choice"
_CHOICE_ATTENDEE_ID = "90010001"
_CHOICE_CLASS_P4_ID = "2000010"
_CHOICE_BADGE = "Chess"

_BLANK_SCOUT = "Sam Nameless"
_BLANK_CLASS_P4_ID = "2000011"
_BLANK_BADGE = "Cooking"


def _requirement_rows() -> list[dict[str, Any]]:
    return [
        {
            "scout_name": _CHOICE_SCOUT,
            "attendee_id": _CHOICE_ATTENDEE_ID,
            "class_p4_id": _CHOICE_CLASS_P4_ID,
            "merit_badge_name": _CHOICE_BADGE,
            "requirement_type_id": "1",
            "requirement_number": "3",
            "description": "Do ONE of the following:",
            "completed_requirement": False,
        },
        {
            "scout_name": _CHOICE_SCOUT,
            "attendee_id": _CHOICE_ATTENDEE_ID,
            "class_p4_id": _CHOICE_CLASS_P4_ID,
            "merit_badge_name": _CHOICE_BADGE,
            "requirement_type_id": "1",
            "requirement_number": "3a",
            "description": "Identify the pieces and how they move.",
            "completed_requirement": True,
        },
        {
            "scout_name": _CHOICE_SCOUT,
            "attendee_id": _CHOICE_ATTENDEE_ID,
            "class_p4_id": _CHOICE_CLASS_P4_ID,
            "merit_badge_name": _CHOICE_BADGE,
            "requirement_type_id": "1",
            "requirement_number": "3b",
            "description": "Demonstrate castling and en passant.",
            "completed_requirement": False,
        },
        {
            "scout_name": _CHOICE_SCOUT,
            "attendee_id": _CHOICE_ATTENDEE_ID,
            "class_p4_id": _CHOICE_CLASS_P4_ID,
            "merit_badge_name": _CHOICE_BADGE,
            "requirement_type_id": "1",
            "requirement_number": "4",
            "description": "Bring a chess set to the first class. (pre-req)",
            "completed_requirement": False,
        },
        {
            "scout_name": _BLANK_SCOUT,
            "attendee_id": "",
            "output_id": "",
            "class_p4_id": _BLANK_CLASS_P4_ID,
            "merit_badge_name": _BLANK_BADGE,
            "requirement_type_id": "1",
            "requirement_number": "5",
            "description": "Plan a menu for a patrol outing.",
            "completed_requirement": False,
        },
    ]


def test_annotate_requirement_statuses_matches_legacy_on_nested_choice_and_blank_identity() -> None:
    rows = _requirement_rows()

    legacy_result = legacy.annotate_requirement_statuses(deepcopy(rows))
    package_result = reporting_service._annotate_requirement_statuses(deepcopy(rows))

    assert legacy_result == package_result

    # Pin real expected values (not just cross-copy agreement) so a future bug that breaks
    # both copies identically still gets caught.
    for result in (legacy_result, package_result):
        parent = next(item for item in result if item["requirement_number"] == "3")
        assert parent["calculated_status"] == "complete_check"
        assert parent["total_subrequirements"] == 2
        assert parent["completed_subrequirements"] == 1
        assert parent["choice_required_count"] == 1
        assert "parent_requirement_number" not in parent

        child = next(item for item in result if item["requirement_number"] == "3b")
        assert child["parent_requirement_number"] == "3"

        blank_identity = next(item for item in result if item["requirement_number"] == "5")
        assert blank_identity["calculated_status"] == "incomplete"


# --- Part 2 fixture -----------------------------------------------------------------------
#
# Built by hand (not derived from Part 1 through group_missing_requirements) so this exercises
# _render_email_text/render_email_text in isolation, not the shared grouping step.

_BADGE_GROUPS: dict[str, list[dict[str, Any]]] = {
    "Chess": [
        {
            "requirement_number": "3",
            "description": "Do ONE of the following:",
            "depth": 0,
            "is_prereq": False,
            "is_leaf": False,
        },
        {
            "requirement_number": "3b",
            "description": "Demonstrate castling and en passant.",
            "depth": 1,
            "is_prereq": False,
            "is_leaf": True,
        },
        {
            "requirement_number": "4",
            "description": "Bring a chess set to the first class.",
            "depth": 0,
            "is_prereq": True,
            "is_leaf": True,
        },
    ]
}


def test_render_email_text_matches_legacy_and_shows_prereq_suffix() -> None:
    legacy_text = legacy.render_email_text("Test Scout", deepcopy(_BADGE_GROUPS))
    package_text = reporting_service._render_email_text("Test Scout", deepcopy(_BADGE_GROUPS))

    assert legacy_text == package_text
    assert "(complete before the event)" in legacy_text
