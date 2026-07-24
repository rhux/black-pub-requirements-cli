"""Builders for legacy record dataclasses. Defaults valid; override per test."""

from __future__ import annotations

from typing import Any

from scout_schedule_cli import ClassRecord, RequirementRecord


def make_requirement(**overrides: Any) -> RequirementRecord:
    defaults: dict[str, Any] = {
        "scout_name": "Avery Archer",
        "attendee_id": "90000001",
        "class_number": "26MB1",
        "class_p4_id": "2000001",
        "merit_badge_name": "Chess",
        "requirement_id": "1001",
        "requirement_type_id": "1",
        "requirement_number": "#1",
        "description": "Discuss the history of chess.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }
    return RequirementRecord(**{**defaults, **overrides})


def make_class(**overrides: Any) -> ClassRecord:
    defaults: dict[str, Any] = {
        "scout_name": "Avery Archer",
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
    return ClassRecord(**{**defaults, **overrides})
