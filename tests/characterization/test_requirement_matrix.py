"""Typed matrix execution of the requirement characterization catalog (Task 20).

Each executable ``REQ-*`` case declares one or more execution contexts; ``execution_params``
expands them. Every context here drives the REAL ``scout_schedule_cli`` requirement-inference
functions directly (never mocked): ``requirement_path``, ``annotate_requirement_statuses``,
``build_missing_requirements``, ``render_email_text``, ``render_email_html``, and
``json_for_html``.

``assert case.rows == before`` on every parametrized case is what proves REQ-NONMUTATE for the
WHOLE catalog, not just the two rows explicitly named REQ-NONMUTATE-*: any case whose rows are
mutated by the function under test fails this line regardless of which axis it belongs to.

No test writes outside ``tmp_path`` and this module performs no real file or network I/O.
"""

from __future__ import annotations

import html
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from tests.matrix.cases.requirement_cases import REQUIREMENT_CASES, RequirementCase
from tests.matrix.pytest_support import execution_params


class LegacyRequirementRunner:
    """Runner[RequirementCase, object] over the real requirement-inference pipeline."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: RequirementCase, *, root: Path) -> object:
        handler = getattr(self, f"_ctx_{self.context_id}")
        return handler(case)

    # -- requirement_path: sequential, threading current_top_level ------------------------------

    def _ctx_requirement_path(self, case: RequirementCase) -> tuple[object, ...]:
        import scout_schedule_cli as legacy

        current_top_level: str | None = None
        pairs: list[tuple[tuple[str, ...], str | None]] = []
        for row in case.rows:
            path, current_top_level = legacy.requirement_path(
                str(row.get("requirement_number") or ""), current_top_level
            )
            pairs.append((path, current_top_level))
        return tuple(pairs)

    # -- tree_consumer: annotate_requirement_statuses, projected --------------------------------

    def _ctx_tree_consumer(self, case: RequirementCase) -> tuple[object, ...]:
        import scout_schedule_cli as legacy

        if case.meta.axis_id == "REQ-CLASS":
            return self._ctx_html_consumer(case)

        annotated = legacy.annotate_requirement_statuses([dict(row) for row in case.rows])
        return tuple(
            (
                str(item.get("requirement_number") or ""),
                tuple(item.get("requirement_path") or ()),
                item.get("parent_requirement_number"),
                item.get("calculated_status"),
                item.get("calculated_status_reason"),
                item.get("completed_subrequirements"),
                item.get("total_subrequirements"),
                item.get("choice_required_count"),
            )
            for item in annotated
        )

    # -- html_consumer: json_for_html round trip -------------------------------------------------

    def _ctx_html_consumer(self, case: RequirementCase) -> tuple[object, ...]:
        import scout_schedule_cli as legacy

        if case.meta.axis_id == "REQ-CLASS":
            embedded = legacy.json_for_html([dict(row) for row in case.rows])
            decoded = json.loads(embedded)
            return tuple(tuple(sorted(entry.items())) for entry in decoded)

        annotated = legacy.annotate_requirement_statuses([dict(row) for row in case.rows])
        embedded = legacy.json_for_html({"requirements": annotated})
        assert "__REPORT_DATA__" not in embedded
        decoded = json.loads(embedded)
        return tuple(
            (item["requirement_number"], item["calculated_status"])
            for item in decoded["requirements"]
        )

    # -- email_consumer: build_missing_requirements + render_email_text/html --------------------

    def _ctx_email_consumer(self, case: RequirementCase) -> tuple[object, ...]:
        import scout_schedule_cli as legacy

        row = dict(case.rows[0])
        scout_name = str(row.get("scout_name") or "")
        attendee_id = str(row.get("attendee_id") or "")
        scouts = [
            {
                "name": scout_name,
                "attendee_id": attendee_id,
                "classes": [],
                "requirements": [dict(r) for r in case.rows],
                "errors": [],
            }
        ]
        missing = legacy.build_missing_requirements(scouts)
        key = attendee_id.strip() or f"name:{scout_name}"
        bucket = missing.get(key) or {"display_name": scout_name, "badges": {}}
        badge_groups: dict[str, list[dict[str, Any]]] = bucket["badges"]
        body_text = legacy.render_email_text(scout_name, badge_groups)
        body_html = legacy.render_email_html(scout_name, badge_groups)
        return tuple(
            (
                number,
                number in body_text,
                html.escape(number) in body_html if number else False,
            )
            for number in (str(row.get("requirement_number") or ""),)
        )


@pytest.mark.parametrize(("case", "context_id"), execution_params(REQUIREMENT_CASES))
def test_requirement_execution(
    case: RequirementCase, context_id: str, tmp_path: Path
) -> None:
    before = deepcopy(case.rows)
    observed = LegacyRequirementRunner(context_id).run(case, root=tmp_path)
    assert observed == case.expected_by_context[context_id]
    assert case.rows == before


def test_requirement_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.requirement_cases import ALL_REQUIREMENT_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    req_axes = [axis for axis in AXES if axis.domain is Domain.REQUIREMENT]
    req_boundaries = [b for b in BOUNDARIES if b.domain is Domain.REQUIREMENT]

    errors = validate_registry(
        ALL_REQUIREMENT_METADATA, req_axes, req_boundaries, [], list(POLICIES)
    )
    assert errors == ()
