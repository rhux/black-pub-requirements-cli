"""Boundary parsing and versioned serialization for the record shapes.

Free functions, not methods: core/models.py stays dependency-free and the operational and
shareable projections differ by one parameter instead of two class hierarchies.

Coercion here reproduces the legacy boundary EXACTLY -- str(x or "") and truthy(). Making it
stricter is the ACQ-REQ-004 behavior change and belongs to Slice 2b.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult
from scoutmb.errors import ScoutmbError

SCHEMA_VERSION = 1
_SUPPORTED_VERSIONS = frozenset({1})


class UnsupportedSchemaVersion(ScoutmbError):
    """A payload declared a schema version this build cannot read. Fails closed."""


def check_schema_version(version: int) -> None:
    # `type(version) is int` (not isinstance, not ==) is deliberate: bool is an int subclass
    # (isinstance(True, int) is True) and 1.0 == 1, so either check would let a bool or float
    # masquerade as schema version 1 and defeat "fail closed".
    if type(version) is not int or version not in _SUPPORTED_VERSIONS:
        raise UnsupportedSchemaVersion(
            f"Schema version {version!r} is not supported (this build reads "
            f"{sorted(_SUPPORTED_VERSIONS)})."
        )


def _text(value: Any) -> str:
    """str(x or "") -- NO strip.

    The legacy construction in process_scout strips exactly ONE field (present_days) and
    leaves every other text field unstripped. Stripping here would be a silent behavior
    change to every ACQ-REQ-* and ART-SCHEMA-* expectation.
    """
    return str(value or "")


def _flag(value: Any) -> bool:
    """truthy() semantics, not bool().

    The legacy construction uses truthy(), so the string "0" is FALSE. bool("0") is True --
    a non-empty string -- which would invert completed_requirement for every payload that
    arrives as raw upstream text rather than an already-parsed bool.
    """
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def requirement_from_mapping(data: Mapping[str, Any]) -> RequirementRecord:
    """Parse a RECORD-SHAPED mapping (the output of to_row / asdict) back into a record.

    Scope matters. This is NOT the upstream-payload parser: the legacy construction at
    scout_schedule_cli.py:607-621 reads UPPERCASE ScoutingEvent keys and runs
    `clean_html_description` over REQ_DESCR, and reproducing that here would double-clean an
    already-clean description on the shim path.

    Slice 2b's gateway owns `requirement_from_upstream_payload`, which maps the upstream keys,
    applies clean_html_description, and then delegates here. The coercions below still match
    the legacy ones field for field so that the shared half stays honest -- `str(x or "")` with
    no strip except present_days, and truthy() for flags.
    """
    return RequirementRecord(
        scout_name=_text(data.get("scout_name")),
        attendee_id=_text(data.get("attendee_id")),
        class_number=_text(data.get("class_number")),
        class_p4_id=_text(data.get("class_p4_id")),
        merit_badge_name=_text(data.get("merit_badge_name")),
        requirement_id=_text(data.get("requirement_id")),
        requirement_type_id=_text(data.get("requirement_type_id")),
        requirement_number=_text(data.get("requirement_number")),
        description=str(data.get("description") or ""),
        completed_requirement=_flag(data.get("completed_requirement")),
        completed_class=_flag(data.get("completed_class")),
        requirement_on_event=_flag(data.get("requirement_on_event")),
        present_days=_text(data.get("present_days")).strip(),
    )


def requirement_to_row(
    record: RequirementRecord, *, shareable: bool, output_id: str | None = None
) -> dict[str, Any]:
    """Project a RequirementRecord into a plain dict, in declaration-field order.

    ``shareable=True`` drops ``attendee_id`` (the upstream bearer token) and substitutes
    ``output_id`` IN PLACE of it -- same index, so the row is a deletion plus an insertion,
    never a reordering. ``output_id`` is ``None`` for an attempt that failed before identity
    resolution; callers must pass the per-run output id resolved via ``RunIdentity``, never a
    placeholder string. Ignored when ``shareable=False``.
    """
    row = {field.name: getattr(record, field.name) for field in fields(RequirementRecord)}
    return _project(row, shareable=shareable, output_id=output_id)


def class_from_mapping(data: Mapping[str, Any]) -> ClassRecord:
    """Mirror of the legacy ClassRecord construction. Read scout_schedule_cli.py's
    ClassRecord(...) call site and match its per-field coercion before editing this."""
    return ClassRecord(
        scout_name=_text(data.get("scout_name")),
        attendee_id=_text(data.get("attendee_id")),
        class_number=_text(data.get("class_number")),
        class_p4_id=_text(data.get("class_p4_id")),
        class_name=_text(data.get("class_name")),
        days=_text(data.get("days")),
        period_name=_text(data.get("period_name")),
        start_time=_text(data.get("start_time")),
        start_time_24h=_text(data.get("start_time_24h")),
        location=_text(data.get("location")),
        has_requirements=_flag(data.get("has_requirements")),
        class_completed=_flag(data.get("class_completed")),
        raw_class_name=str(data.get("raw_class_name") or ""),
    )


def class_to_row(
    record: ClassRecord, *, shareable: bool, output_id: str | None = None
) -> dict[str, Any]:
    """Project a ClassRecord into a plain dict, in declaration-field order.

    ``shareable=True`` drops ``attendee_id`` (the upstream bearer token) and substitutes
    ``output_id`` IN PLACE of it -- same index, so the row is a deletion plus an insertion,
    never a reordering. ``output_id`` is ``None`` for an attempt that failed before identity
    resolution; callers must pass the per-run output id resolved via ``RunIdentity``, never a
    placeholder string. Ignored when ``shareable=False``.
    """
    row = {field.name: getattr(record, field.name) for field in fields(ClassRecord)}
    return _project(row, shareable=shareable, output_id=output_id)


def scout_result_to_row(record: ScoutResult) -> dict[str, Any]:
    """Operational only: scouts.json is operational-private and keeps qr_url + attendee_id."""
    return {
        "name": record.name,
        "qr_url": record.qr_url,
        "attendee_id": record.attendee_id,
        "classes": [class_to_row(item, shareable=False) for item in record.classes],
        "requirements": [requirement_to_row(item, shareable=False) for item in record.requirements],
        "errors": list(record.errors),
    }


def scout_result_from_row(data: Mapping[str, Any]) -> ScoutResult:
    """Reverse of scout_result_to_row -- reconstructs a ScoutResult from its scouts.json-shaped
    row. Used by the checkpoint store's completed_results (Task B5.3/B5.5): a resumed run
    rebuilds each previously-completed scout's ScoutResult from what was saved, rather than
    re-fetching it or silently dropping it from the resumed run's report."""
    return ScoutResult(
        name=_text(data.get("name")),
        qr_url=_text(data.get("qr_url")),
        attendee_id=_text(data.get("attendee_id")),
        classes=tuple(class_from_mapping(row) for row in data.get("classes") or ()),
        requirements=tuple(requirement_from_mapping(row) for row in data.get("requirements") or ()),
        errors=tuple(str(item) for item in data.get("errors") or ()),
    )


def json_for_html(value: Any) -> str:
    """Serialize JSON safely for embedding inside an HTML script element."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _project(
    row: dict[str, Any], *, shareable: bool, output_id: str | None = None
) -> dict[str, Any]:
    """Normalize collections; substitute identity when the projection is shareable.

    asdict preserves tuples, so anything sequence-shaped is normalized here rather than left
    for json.dumps to paper over -- a CSV cell would otherwise receive a tuple repr.

    attendee_id is REPLACED IN PLACE by output_id -- same index, so the shareable row is a
    deletion plus an insertion, never a reordering. output_id is None for an attempt that
    failed before identity resolution; never a placeholder string, never an omitted key.
    """
    projected: dict[str, Any] = {}
    for key, value in row.items():
        if shareable and key == "attendee_id":
            projected["output_id"] = output_id
            continue
        projected[key] = list(value) if isinstance(value, tuple) else value
    return projected
