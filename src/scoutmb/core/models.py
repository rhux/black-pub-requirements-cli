"""Frozen record shapes. No logic, no serialization, no I/O.

Serialization lives in core/output_schemas.py as free functions, which is what keeps this
module dependency-free and keeps `models.py` from becoming the place everything imports.

Field DECLARATION ORDER is a shipped contract: classes.csv and requirements.csv take their
header from __dataclass_fields__ (ART-SCHEMA-002, ART-SCHEMA-003). Do not reorder, and do not
add a field except at the end with a default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Shared by scoutmb.adapters.pdf.extract and scoutmb.features.ingest.pdf_extract -- both
# layers need the exact same literal (one filters candidate QR values, the other filters
# retained CSV rows), and Task 16 already fixed one drift incident from these two modules
# each keeping their own copy. Hoisted here, alongside ExtractedAttendee/ExtractionError, for
# the same cross-layer-sharing reason: neither adapters nor features may import the other, but
# both may import core.
SCOUTINGEVENT_PREFIX = "https://scoutingevent.com/mobile/"


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


@dataclass(slots=True)
class ExtractedAttendee:
    """Stage-1 (PDF) extraction record. Shared by adapters/pdf/pages.py (which builds these)
    and features/ingest/pdf_extract.py (which writes them out) -- neither layer may import the
    other, so the shape they both need lives here in core, not in either of them."""

    attendee_name: str
    name_as_printed: str
    registrant_type: str
    qr_data: str
    source_pdf: str
    pdf_page: int
    qr_decode_method: str


@dataclass(slots=True)
class ExtractionError:
    """Stage-1 (PDF) extraction error record. See ExtractedAttendee for why this lives here."""

    source_pdf: str
    pdf_page: int
    attendee_name: str
    registrant_type: str
    error: str
