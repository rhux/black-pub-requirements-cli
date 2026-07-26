"""REQ-DUP observation: which ancestor row build_missing_requirements actually selected.

Runs against the LEGACY implementation in this task. Task 13 adds a package runner over the
same two cases; both must produce the same tuple.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.matrix.cases.requirement_cases import REQUIREMENT_DUP_CASES, RequirementCase
from tests.matrix.pytest_support import execution_params


def observe_selection(grouped: dict[str, Any], case: RequirementCase) -> tuple[object, ...]:
    """Normalize a build_missing_requirements-shaped result into a comparable tuple.

    Takes the GROUPED RESULT, not a module: the legacy and package sides reach it by
    different routes, and a `module.build_missing_requirements(...)` parameter would
    silently require the package to grow a function it does not have.
    """
    row = dict(case.rows[0])
    bucket = grouped.get(str(row["attendee_id"])) or {"badges": {}}
    entries = [entry for items in bucket["badges"].values() for entry in items]
    return tuple(
        (e["requirement_number"], e["description"], e["depth"], e["is_leaf"])
        for e in sorted(entries, key=lambda e: (e["requirement_number"], e["description"]))
    )


def _scouts_payload(case: RequirementCase) -> list[dict[str, Any]]:
    row = dict(case.rows[0])
    return [
        {
            "name": row["scout_name"],
            "attendee_id": row["attendee_id"],
            "classes": [],
            "requirements": [dict(r) for r in case.rows],
            "errors": [],
        }
    ]


@pytest.mark.parametrize(("case", "context_id"), execution_params(REQUIREMENT_DUP_CASES))
def test_legacy_selection(case: RequirementCase, context_id: str) -> None:
    import scout_schedule_cli as legacy

    grouped = legacy.build_missing_requirements(_scouts_payload(case))
    assert observe_selection(grouped, case) == case.expected_by_context[context_id]


@pytest.mark.parametrize(("case", "context_id"), execution_params(REQUIREMENT_DUP_CASES))
def test_package_selection_matches_legacy(case: RequirementCase, context_id: str) -> None:
    """The whole point of REQ-DUP-002: a naive index substitution answers this differently."""
    import scout_schedule_cli as legacy

    from scoutmb.core.inference.missing import group_missing_requirements

    annotated = legacy.annotate_requirement_statuses(
        [dict(r) for scout in _scouts_payload(case) for r in scout["requirements"]]
    )
    package_grouped = group_missing_requirements(
        annotated,
        attendee_key_of=legacy._attendee_key_for,
        clean_description=legacy.clean_html_description,
    )
    legacy_grouped = legacy.build_missing_requirements(_scouts_payload(case))

    assert observe_selection(package_grouped, case) == observe_selection(legacy_grouped, case)
    assert observe_selection(package_grouped, case) == case.expected_by_context[context_id]
