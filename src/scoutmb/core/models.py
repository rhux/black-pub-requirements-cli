"""Frozen record shapes. No logic, no serialization, no I/O.

Serialization lives in core/output_schemas.py as free functions, which is what keeps this
module dependency-free and keeps `models.py` from becoming the place everything imports.

Field DECLARATION ORDER is a shipped contract: classes.csv and requirements.csv take their
header from __dataclass_fields__ (ART-SCHEMA-002, ART-SCHEMA-003). Do not reorder, and do not
add a field except at the end with a default.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScoutInput:
    """Deliberately MUTABLE, unlike the other records.

    legacy load_inputs strips url/name/registrant_type in place on each instance. Freezing
    this shape is a behavior change to the loader, which Task 15 makes explicitly; until then
    the mutable shape is what the catalog's input cases exercise.
    """

    name: str
    url: str
    registrant_type: str = ""


@dataclass(frozen=True, slots=True)
class ClassRecord:
    scout_name: str
    attendee_id: str
    class_number: str
    class_p4_id: str
    class_name: str
    days: str
    period_name: str
    start_time: str
    start_time_24h: str
    location: str
    has_requirements: bool
    class_completed: bool
    raw_class_name: str


@dataclass(frozen=True, slots=True)
class RequirementRecord:
    scout_name: str
    attendee_id: str
    class_number: str
    class_p4_id: str
    merit_badge_name: str
    requirement_id: str
    requirement_type_id: str
    requirement_number: str
    description: str
    completed_requirement: bool
    completed_class: bool
    requirement_on_event: bool
    present_days: str


@dataclass(frozen=True, slots=True)
class ScoutResult:
    name: str
    qr_url: str
    attendee_id: str = ""
    classes: tuple[ClassRecord, ...] = field(default_factory=tuple)
    requirements: tuple[RequirementRecord, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
