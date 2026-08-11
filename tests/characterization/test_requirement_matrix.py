"""Drives ``tests/matrix/cases/requirement_cases.py``'s ``REQUIREMENT_CASES`` catalog against
the REAL package requirement-inference code, one test per declared (case_id, context_id) pair
via ``execution_params``. This is the runner the catalog's own module docstring names
(``tests/characterization/test_requirement_matrix.py``); it was deleted in Slice 2b alongside
the flat ``scout_schedule_cli.py`` characterization files and is recreated here against the
package equivalents (``scoutmb.core.inference.numbering``/``...features.reporting.service``).

``REQUIREMENT_DUP_CASES`` (the REQ-DUP-* cases, "missing_selection" context) is deliberately
NOT driven here -- see requirement_cases.py's own module-level comment for why -- and has its
own runner in ``tests/parity/test_missing_selection.py``.

Every dispatch below calls the real function; nothing here re-derives expected values, it only
projects the real return value into the shape ``expected_by_context`` already states (computed
by hand against the source, per the catalog's docstring).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.matrix.cases.requirement_cases import REQUIREMENT_CASES, RequirementCase
from tests.matrix.pytest_support import execution_params

from scoutmb.core.inference.numbering import requirement_path
from scoutmb.core.output_schemas import json_for_html
from scoutmb.features.reporting.service import (
    _annotate_requirement_statuses as annotate_requirement_statuses,
)
from scoutmb.features.reporting.service import (
    _build_missing_requirements as build_missing_requirements,
)
from scoutmb.features.reporting.service import _render_email_html as render_email_html
from scoutmb.features.reporting.service import _render_email_text as render_email_text


def _ctx_requirement_path(case: RequirementCase) -> tuple[object, ...]:
    current_top_level: str | None = None
    observed: list[tuple[object, object]] = []
    for row in case.rows:
        path, current_top_level = requirement_path(
            str(row.get("requirement_number") or ""), current_top_level
        )
        observed.append((path, current_top_level))
    return tuple(observed)


def _project_tree_row(item: dict[str, Any]) -> tuple[object, ...]:
    return (
        item.get("requirement_number"),
        tuple(item.get("requirement_path") or ()),
        item.get("parent_requirement_number"),
        item.get("calculated_status"),
        item.get("calculated_status_reason"),
        item.get("completed_subrequirements"),
        item.get("total_subrequirements"),
        item.get("choice_required_count"),
    )


def _ctx_tree_consumer(case: RequirementCase) -> tuple[object, ...]:
    annotated = annotate_requirement_statuses(list(case.rows))
    return tuple(_project_tree_row(item) for item in annotated)


def _ctx_html_consumer(case: RequirementCase) -> tuple[object, ...]:
    if case.meta.axis_id == "REQ-CLASS":
        # REQ-CLASS characterizes ClassRecord.class_completed passthrough, not requirement
        # inference: round-trip the raw class rows directly through the same safe-embed
        # function requirement rows use, per requirement_cases.py's own module docstring.
        rows = json.loads(json_for_html(list(case.rows)))
        return tuple(tuple(sorted(row.items())) for row in rows)

    annotated = annotate_requirement_statuses(list(case.rows))
    rows = json.loads(json_for_html(annotated))
    return tuple((row["requirement_number"], row["calculated_status"]) for row in rows)


def _ctx_email_consumer(case: RequirementCase) -> tuple[object, ...]:
    scout_name = str(case.rows[0].get("scout_name") or "")
    attendee_id = str(case.rows[0].get("attendee_id") or "")
    scout = {
        "name": scout_name,
        "attendee_id": attendee_id,
        "classes": [],
        "requirements": [dict(row) for row in case.rows],
        "errors": [],
    }
    missing = build_missing_requirements([scout])
    key = attendee_id.strip() or f"name:{scout_name}"
    bucket = missing.get(key, {"display_name": scout_name, "badges": {}})
    badge_groups = bucket["badges"]
    text = render_email_text(scout_name, badge_groups)
    html_body = render_email_html(scout_name, badge_groups)
    return tuple(
        (
            str(row.get("requirement_number") or ""),
            str(row.get("requirement_number") or "") in text,
            str(row.get("requirement_number") or "") in html_body,
        )
        for row in case.rows
    )


_DISPATCH = {
    "requirement_path": _ctx_requirement_path,
    "tree_consumer": _ctx_tree_consumer,
    "html_consumer": _ctx_html_consumer,
    "email_consumer": _ctx_email_consumer,
}


@pytest.mark.parametrize(("case", "context_id"), execution_params(REQUIREMENT_CASES))
def test_requirement_matrix(case: RequirementCase, context_id: str) -> None:
    before = tuple(dict(row) for row in case.rows)

    handler = _DISPATCH.get(context_id)
    if handler is None:
        pytest.fail(f"{case.meta.case_id}: no runner dispatch for context {context_id!r}")

    observed = handler(case)

    # Blanket non-mutation check (requirement_cases.py's module docstring: "asserted for EVERY
    # case in this catalog by the test harness's blanket assert case.rows == before"), proving
    # no dispatch path above ever hands the real code an object it goes on to mutate in place.
    assert tuple(dict(row) for row in case.rows) == before

    assert observed == case.expected_by_context[context_id]
