"""The schema-drift boundary (ACQ-REQ-004, D22). Two required identity fields; every other
field keeps the legacy str(x or "") / truthy() coercion from core/output_schemas.py; description
is clean_html_description-cleaned, matching process_scout's existing construction exactly
(scout_schedule_cli.py:459) -- dropping that would leave every requirement description carrying
raw <br> tags and HTML entities instead of the cleaned text the rest of the codebase relies on.

clean_html_description is duplicated here rather than imported, matching the precedent already
established between scout_schedule_cli.py and features/reporting/service.py's own
_clean_html_description (that module's docstring: 'duplicate scout_schedule_cli.py's same-named
functions rather than importing them... kept in lockstep by inspection') -- this module is a
THIRD copy for the same reason: it must not import back from the flat script, and the package
has no shared home for this one small helper yet.
"""

from __future__ import annotations

import html
import re
from typing import Any

from scoutmb.errors import ScoutmbError

_SAMPLE_LIMIT = 300
_SENSITIVE_KEY_MARKERS = ("COOKIE", "SESSION", "TOKEN", "AUTH")


class ScoutingEventSchemaDrift(ScoutmbError):
    """A requirement row from ScoutingEvent is missing a field this build treats as required.
    Carries a bounded sample with any key whose name looks sensitive redacted -- never the raw
    payload, which may carry other rows' data alongside the offending one."""

    def __init__(self, *, profile: str, missing_fields: tuple[str, ...], sample: str) -> None:
        self.profile = profile
        self.missing_fields = missing_fields
        self.sample = sample[:_SAMPLE_LIMIT]
        super().__init__(
            f"{profile} is missing required field(s) {', '.join(missing_fields)}: {self.sample}"
        )


def _redacted_sample(row: dict[str, Any]) -> str:
    """repr() of the row with any value whose KEY name contains a sensitive marker replaced by
    'REDACTED' before truncation -- truncation alone (an earlier draft's only protection) still
    lets a sensitive field's value leak if it happens to sort near the start of the dict."""
    redacted = {
        key: "REDACTED"
        if any(marker in key.upper() for marker in _SENSITIVE_KEY_MARKERS)
        else value
        for key, value in row.items()
    }
    return repr(redacted)


def _text(value: Any) -> str:
    return str(value or "")


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _clean_html_description(value: str) -> str:
    """Exact mirror of scout_schedule_cli.clean_html_description (lines 208-214)."""
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def validate_requirement_row(row: dict[str, Any]) -> dict[str, Any]:
    """Raise ScoutingEventSchemaDrift if requirement_id or requirement_number cannot be
    resolved; otherwise return the same field set process_scout already builds a
    RequirementRecord from, coerced exactly as core/output_schemas.py does, with description
    cleaned exactly as process_scout already cleans it."""
    missing: list[str] = []

    requirement_id = _text(row.get("MDM_LKP_BADGE_REQ_ID"))
    if not requirement_id:
        missing.append("requirement_id")

    requirement_number = _text(row.get("REQ_NBR_WEB_DISPLAY")) or _text(row.get("REQ_NBR"))
    if not requirement_number:
        missing.append("requirement_number")

    if missing:
        raise ScoutingEventSchemaDrift(
            profile="requirement_row", missing_fields=tuple(missing), sample=_redacted_sample(row)
        )

    return {
        "merit_badge_name": _text(row.get("MERIT_BADGE_NAME")),
        "requirement_id": requirement_id,
        "requirement_type_id": _text(row.get("MDM_LKP_BADGE_REQ_TYPE_ID")),
        "requirement_number": requirement_number,
        "description": _clean_html_description(_text(row.get("REQ_DESCR"))),
        "completed_requirement": _flag(row.get("COMPLETED_REQ_FLAG")),
        "completed_class": _flag(row.get("COMPLETED_CLASS_FLAG")),
        "requirement_on_event": _flag(row.get("REQ_ON_EVENT")),
        "present_days": _text(row.get("PRESENT_DAYS")).strip(),
    }
