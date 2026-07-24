from __future__ import annotations

from dataclasses import asdict

from scout_schedule_cli import build_missing_requirements
from tests.factories.records import make_requirement


def _scout(aid, rid, num):
    return {
        "name": "Avery Archer",
        "attendee_id": aid,
        "classes": [],
        "errors": [],
        "requirements": [
            asdict(
                make_requirement(
                    attendee_id=aid,
                    requirement_id=rid,
                    requirement_number=num,
                    merit_badge_name="Chess",
                )
            )
        ],
    }


def test_same_named_attendees_stay_separate():
    grouped = build_missing_requirements(
        [_scout("90000001", "r1", "#1"), _scout("90000002", "r2", "#2")]
    )
    assert len(grouped) == 2
    for entry in grouped.values():
        assert entry["display_name"] == "Avery Archer"
        assert len(entry["badges"]["Chess"]) == 1
