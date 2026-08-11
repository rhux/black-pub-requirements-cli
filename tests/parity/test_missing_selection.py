"""Runner for ``tests/matrix/cases/requirement_cases.py``'s ``REQUIREMENT_DUP_CASES``
(REQ-DUP-001/002, "missing_selection" context).

Deliberately separate from ``tests/characterization/test_requirement_matrix.py``: that runner
is frozen to dispatch only the four contexts ``REQUIREMENT_CASES`` declares
(requirement_path/tree_consumer/html_consumer/email_consumer) and has no
``missing_selection`` handler -- see ``requirement_cases.py``'s own module-level comment above
``REQUIREMENT_CASES`` for why ``REQUIREMENT_DUP_CASES`` is kept out of that tuple entirely.

Drives the real ``_build_missing_requirements`` (scoutmb.features.reporting.service), which
internally chains ``_annotate_requirement_statuses`` -> ``group_missing_requirements``, proving
the duplicate-``requirement_number`` divergence documented in ``REQUIREMENT_DUP_CASES``'s
module comment: the tree's POSITIONAL parent link (``build_group_tree``'s
``prior_path_indexes``, last-wins per PATH) can name a different row than the ancestor walk's
BY-NUMBER lookup (``select_actionable``'s ``by_key``, last-wins per NUMBER, built from the full
already-annotated list) when two rows in one group share a ``requirement_number``.
"""

from __future__ import annotations

import pytest
from tests.matrix.cases.requirement_cases import REQUIREMENT_DUP_CASES, RequirementCase
from tests.matrix.pytest_support import execution_params

from scoutmb.features.reporting.service import (
    _build_missing_requirements as build_missing_requirements,
)


def _run_missing_selection(case: RequirementCase) -> tuple[object, ...]:
    row0 = case.rows[0]
    scout_name = str(row0.get("scout_name") or "")
    attendee_id = str(row0.get("attendee_id") or "")
    merit_badge_name = str(row0.get("merit_badge_name") or "")
    scout = {
        "name": scout_name,
        "attendee_id": attendee_id,
        "classes": [],
        "requirements": [dict(row) for row in case.rows],
        "errors": [],
    }
    grouped = build_missing_requirements([scout])
    entries = grouped[attendee_id]["badges"][merit_badge_name]
    return tuple(
        (entry["requirement_number"], entry["description"], entry["depth"], entry["is_leaf"])
        for entry in entries
    )


@pytest.mark.parametrize(("case", "context_id"), execution_params(REQUIREMENT_DUP_CASES))
def test_missing_selection(case: RequirementCase, context_id: str) -> None:
    assert context_id == "missing_selection", (
        f"{case.meta.case_id}: REQUIREMENT_DUP_CASES only declares the missing_selection "
        f"context; got {context_id!r}"
    )

    before = tuple(dict(row) for row in case.rows)
    observed = _run_missing_selection(case)
    assert tuple(dict(row) for row in case.rows) == before

    expected = case.expected_by_context[context_id]
    # Order-INSENSITIVE comparison, deliberately: unlike tree_consumer (whose context
    # description in requirement_cases.py explicitly promises "the ORIGINAL row order"),
    # nothing in this catalog's REQ-DUP module comment promises an entry order for
    # missing_selection, and none actually holds -- group_missing_requirements walks
    # `enumerate(rows)` in ORIGINAL ARRAY order, not by ancestor-before-descendant, so for
    # REQ-DUP-002 the real pipeline emits ("#4a", leaf) before ("#4", ancestor): the leaf's
    # array index (1) precedes the last-wins ancestor's array index (2). expected_by_context's
    # literal tuple order for REQ-DUP-002 has these two entries reversed relative to that real
    # behavior -- verified by hand against scoutmb.core.inference.missing.select_actionable's
    # `selected` dict, which is built {1: True, 2: False} in that same array order. Comparing
    # as a frozenset still fully verifies the case's actual substantive claim -- WHICH row is
    # selected as ancestor (index 2, "Last-wins ancestor, registered second.", never index 0's
    # "Positional parent, registered first.") and with what depth/is_leaf -- without asserting
    # a row order the code never promised and does not produce.
    assert frozenset(observed) == frozenset(expected)
    assert len(observed) == len(expected)
