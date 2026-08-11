from __future__ import annotations

import csv

from tests.factories.records import make_class, make_requirement

from scoutmb.adapters.files.atomic import write_csv
from scoutmb.core.models import ClassRecord, RequirementRecord

CLASS_HEADER = [
    "scout_name",
    "attendee_id",
    "class_number",
    "class_p4_id",
    "class_name",
    "days",
    "period_name",
    "start_time",
    "start_time_24h",
    "location",
    "has_requirements",
    "class_completed",
    "raw_class_name",
]
REQ_HEADER = [
    "scout_name",
    "attendee_id",
    "class_number",
    "class_p4_id",
    "merit_badge_name",
    "requirement_id",
    "requirement_type_id",
    "requirement_number",
    "description",
    "completed_requirement",
    "completed_class",
    "requirement_on_event",
    "present_days",
]


def _header(path):
    with path.open("r", encoding="utf-8-sig", newline="") as s:
        return next(csv.reader(s))


def test_class_csv_header_stable(tmp_path):
    p = tmp_path / "c.csv"
    write_csv(p, [make_class()], [f.name for f in ClassRecord.__dataclass_fields__.values()])
    assert _header(p) == CLASS_HEADER


def test_requirement_csv_header_stable(tmp_path):
    p = tmp_path / "r.csv"
    write_csv(
        p, [make_requirement()], [f.name for f in RequirementRecord.__dataclass_fields__.values()]
    )
    assert _header(p) == REQ_HEADER
