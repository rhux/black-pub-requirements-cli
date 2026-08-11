"""Pin inference before decomposition. KNOWN_DEFECT pins today's WRONG merge on purpose."""

from __future__ import annotations

from dataclasses import asdict

from tests.factories.records import make_requirement

from scoutmb.core.inference.numbering import choice_requirement_count
from scoutmb.features.reporting.service import (
    _annotate_requirement_statuses as annotate_requirement_statuses,
)
from scoutmb.features.reporting.service import (
    _build_missing_requirements as build_missing_requirements,
)


def test_annotate_does_not_mutate_input():
    rows = [asdict(make_requirement(requirement_number="#1"))]
    before = [dict(r) for r in rows]
    annotate_requirement_statuses(rows)
    assert rows == before


def test_choice_parent_completes_at_threshold():
    rows = [
        asdict(
            make_requirement(
                requirement_number="#2", requirement_id="p", description="Do TWO of the following."
            )
        ),
        asdict(
            make_requirement(
                requirement_number="#2a", requirement_id="c1", completed_requirement=True
            )
        ),
        asdict(
            make_requirement(
                requirement_number="#2b", requirement_id="c2", completed_requirement=True
            )
        ),
        asdict(make_requirement(requirement_number="#2c", requirement_id="c3")),
    ]
    parent = next(r for r in annotate_requirement_statuses(rows) if r["requirement_id"] == "p")
    assert parent["choice_required_count"] == 2
    assert parent["calculated_status"] == "complete_check"


def test_choice_count_handles_corpus_verbs():
    assert choice_requirement_count("Do TWO of the following.") == 2
    assert choice_requirement_count("Choose ONE of the following options.") == 1
    assert choice_requirement_count("Select two of the following.") == 2
    assert choice_requirement_count("Explain the following terms") is None


def _scout(reqs):
    return {
        "name": "Avery Archer",
        "attendee_id": "90000001",
        "classes": [],
        "requirements": reqs,
        "errors": [],
    }


def test_leaf_and_ancestor_selection():
    reqs = [
        asdict(
            make_requirement(
                requirement_number="#3", requirement_id="parent", description="Do the following."
            )
        ),
        asdict(make_requirement(requirement_number="#3b", requirement_id="leaf")),
    ]
    entries = build_missing_requirements([_scout(reqs)])["90000001"]["badges"]["Chess"]
    by_num = {e["requirement_number"]: e for e in entries}
    assert by_num["#3b"]["is_leaf"] is True
    assert by_num["#3"]["is_leaf"] is False


def test_headers_and_not_used_excluded():
    reqs = [
        asdict(
            make_requirement(requirement_number="#4", requirement_id="hdr", requirement_type_id="3")
        ),
        asdict(
            make_requirement(
                requirement_number="#5", requirement_id="dead", description="Forge ...(not used)"
            )
        ),
        asdict(make_requirement(requirement_number="#6", requirement_id="live")),
    ]
    nums = {
        e["requirement_number"]
        for e in build_missing_requirements([_scout(reqs)])["90000001"]["badges"]["Chess"]
    }
    assert "#6" in nums and "#4" not in nums and "#5" not in nums
