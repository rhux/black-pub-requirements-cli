"""Synthetic ScoutingEvent-shaped payloads. Field names match the real API."""

from __future__ import annotations

from typing import Any

# All 18 real REQ_NBR_WEB_DISPLAY shapes observed in the corpus (values synthetic).
REQUIREMENT_NUMBER_SHAPES = [
    "#3b",
    "#3(b)",
    "6.a.1.",
    "#5(c)(1)",
    "#1",
    "2.",
    "4",
    "#7a.",
    "#8a(2)",
    "3.b.",
    "#2.Option.A.(1)",
    "#5.Option.D.(3)(a)",
    "#5.Option.A(1)",
    "#5..Opt.A.(1)",
    "#(c)",
    "Note.",
    "",
    "#4..Aaa.A.(1)",
]


def requirement_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "MDM_LKP_BADGE_REQ_ID": "r1",
        "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
        "MERIT_BADGE_NAME": "Chess",
        "REQ_NBR": "1",
        "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Discuss the history of chess.",
        "COMPLETED_REQ_FLAG": "0",
        "COMPLETED_CLASS_FLAG": "0",
        "REQ_ON_EVENT": "1",
        "PRESENT_DAYS": "MoTuWeTh",
    }
    row.update(overrides)
    return row


def requirement_payload(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": {"status": 1, "stack": []}, "data": rows or [requirement_row()]}


def schedule_payload(classes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # Field names MUST match what process_scout reads at scout_schedule_cli.py:515-529:
    # CLASS_NAME (raw), CLASS_NAME_ONLY (display), CLASS_NBR, classP4ID, PERIOD_NAME,
    # CLASS_STIME, STIME, LOCATION_ROOM_NAME, HAS_REQ, CLASS_COMPLETED. The attendee_id
    # is NOT read from the payload — it comes from the request's post_data (form_values).
    # `classes is None` -> one default class; `classes == []` -> a ZERO-class payload
    # (distinguishing None from [] lets Slice 1b characterize the no-class case).
    default = {
        "classP4ID": "2000001",
        "CLASS_NAME": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
        "CLASS_NAME_ONLY": "Chess",
        "CLASS_NBR": "26MB1",
        "PERIOD_NAME": "A Block",
        "CLASS_STIME": "09:00 AM",
        "STIME": "09:00:00",
        "LOCATION_ROOM_NAME": "Pavilion",
        "HAS_REQ": "1",
        "CLASS_COMPLETED": "0",
    }
    rows = [default] if classes is None else classes
    return {"status": {"status": 1}, "data": rows}
