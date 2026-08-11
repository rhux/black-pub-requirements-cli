"""Package-only successor to tests/parity/test_reporting_service_status_parity.py (retired
alongside scout_schedule_cli.py in Slice 2b B10.4). That file's cross-copy comparison against
the legacy script is no longer possible once the legacy script is gone; the "pin real expected
values" half of its assertions -- the only part proving ReportingService's own private helpers
are correct, not just self-consistent with a legacy twin -- is preserved here.

tests/goldens/fixture.py, the only other fixture exercising these helpers, is entirely flat (no
nested parent/child rows, no choice-count wording, no prerequisite-flagged row, no
fully-identity-blank row), so this is genuinely non-redundant coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scoutmb.core.identity import RunIdentity
from scoutmb.features.reporting import service as reporting_service
from scoutmb.interfaces.cli.composition import build_reporting_service

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


def test_annotate_requirement_statuses_nested_choice_and_blank_identity() -> None:
    result = reporting_service._annotate_requirement_statuses(_requirement_rows())

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


def test_render_email_text_shows_prereq_suffix() -> None:
    text = reporting_service._render_email_text("Test Scout", _BADGE_GROUPS)
    assert "(complete before the event)" in text


def test_write_outputs_appends_html_extension_when_missing(tmp_path: Path) -> None:
    """Migrated from tests/characterization/test_phase_a_gap_closure.py."""
    out = tmp_path / "run"
    build_reporting_service().publish(
        out,
        [],
        generated_at_local="2026-01-01 00:00:00",
        generated_at_iso="2026-01-01T00:00:00",
        run_identity=RunIdentity(),
        generate_html=True,
        html_name="report",
    )
    assert (out / "report.html").exists()
