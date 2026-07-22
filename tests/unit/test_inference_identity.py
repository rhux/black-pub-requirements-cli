from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import build_missing_requirements  # noqa: E402
from tests.factories.records import make_requirement  # noqa: E402


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
