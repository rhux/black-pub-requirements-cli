"""Structural self-tests (REG-*): mutate one field of a valid registry, assert the exact
ordered error tuple ``validate_registry`` returns."""

from __future__ import annotations

import dataclasses

from tests.matrix.axes import AxisSpec
from tests.matrix.boundaries import BoundarySpec, BranchExclusion
from tests.matrix.model import (
    CaseMetadata,
    Classification,
    Domain,
    EvidenceKind,
    ExecutionKey,
    Lane,
)
from tests.matrix.policies import SurfacePolicy
from tests.matrix.registry import execution_keys, validate_registry


def make_case(**over: object) -> CaseMetadata:
    base: dict[str, object] = {
        "case_id": "C1",
        "axis_id": "corpus-split",
        "member": "schedule",
        "domain": Domain.CORPUS,
        "classification": Classification.PRESERVE,
        "evidence": EvidenceKind.CORPUS_AGGREGATE,
        "rationale": "schedule rows carry the null flag pair",
        "contexts": ("csv",),
        "lane": Lane.DEFAULT,
        "evidence_reference": "corpus-aggregate:schedule",
        "interaction_ids": frozenset({"mix"}),
        "surface_id": None,
        "target_owner": None,
        "target_observation": None,
    }
    base.update(over)
    return CaseMetadata(**base)  # type: ignore[arg-type]


def make_axis(**over: object) -> AxisSpec:
    base: dict[str, object] = {
        "axis_id": "corpus-split",
        "domain": Domain.CORPUS,
        "members": frozenset({"schedule", "requirement"}),
        "min_focused_cases": 2,
        "interactions": frozenset({"mix"}),
        "boundaries": frozenset({"b1"}),
    }
    base.update(over)
    return AxisSpec(**base)  # type: ignore[arg-type]


def make_boundary(**over: object) -> BoundarySpec:
    base: dict[str, object] = {
        "boundary_id": "b1",
        "qualified_name": "tools.verify_corpus.classify_row",
        "domain": Domain.CORPUS,
        "required_case_ids": frozenset({"C1"}),
    }
    base.update(over)
    return BoundarySpec(**base)  # type: ignore[arg-type]


def make_exclusion(**over: object) -> BranchExclusion:
    base: dict[str, object] = {
        "exclusion_id": "e1",
        "area_id": "corpus",
        "file": "tools/verify_corpus.py",
        "line": 1,
        "branch_to": None,
        "rationale": "the OSError branch is exercised only by CORP-READ-001",
        "review_reference": "design:corpus-execution",
    }
    base.update(over)
    return BranchExclusion(**base)  # type: ignore[arg-type]


def valid_registry() -> tuple[
    list[CaseMetadata],
    list[AxisSpec],
    list[BoundarySpec],
    list[BranchExclusion],
    list[SurfacePolicy],
]:
    c1 = make_case(case_id="C1", member="schedule", contexts=("csv", "xlsx"))
    c2 = make_case(case_id="C2", member="requirement")
    return [c1, c2], [make_axis()], [make_boundary()], [make_exclusion()], []


# --- REG-ID-001 / "same case in two declared contexts passes" ---------------------------
def test_reg_id_001_valid_registry_has_no_errors():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == ()


def test_case_in_two_contexts_yields_two_execution_keys():
    cases, *_ = valid_registry()
    keys = execution_keys(cases, Lane.DEFAULT)
    assert ExecutionKey("C1", "csv") in keys
    assert ExecutionKey("C1", "xlsx") in keys
    assert ExecutionKey("C2", "csv") in keys
    assert len(keys) == 3


# --- REG-ID-002 duplicate case IDs ------------------------------------------------------
def test_reg_id_002_duplicate_case_ids_fail():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[1] = dataclasses.replace(cases[1], case_id="C1")  # collide with cases[0]
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-ID duplicate case: C1",
    )


# --- REG-AXIS-001 unknown axis ----------------------------------------------------------
def test_reg_axis_001_unknown_axis_fails():
    # Permissive axis so dropping the mutated case from the axis does not cascade.
    axis = make_axis(members=frozenset({"schedule"}), min_focused_cases=1, boundaries=frozenset())
    cases = [make_case(case_id="C1"), make_case(case_id="C2")]
    cases[1] = dataclasses.replace(cases[1], axis_id="ghost")
    assert validate_registry(cases, [axis], [], [make_exclusion()], []) == (
        "REG-AXIS unknown axis: C2:ghost",
    )


# --- REG-AXIS-002 missing member --------------------------------------------------------
def test_reg_axis_002_missing_member_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[1] = dataclasses.replace(cases[1], member="schedule")  # "requirement" now unobserved
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-AXIS missing member: corpus-split:requirement",
    )


# --- REG-AXIS-003 fewer than two focused cases ------------------------------------------
def test_reg_axis_003_too_few_cases_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    axes[0] = dataclasses.replace(axes[0], min_focused_cases=3)  # only 2 cases declared
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-AXIS too few cases: corpus-split",
    )


# --- REG-AXIS-004 missing interaction ---------------------------------------------------
def test_reg_axis_004_missing_interaction_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    axes[0] = dataclasses.replace(axes[0], interactions=frozenset({"mix", "overlap"}))
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-AXIS missing interaction: corpus-split:overlap",
    )


# --- REG-AXIS-005 unmapped boundary -----------------------------------------------------
def test_reg_axis_005_unmapped_boundary_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    boundaries[0] = dataclasses.replace(boundaries[0], required_case_ids=frozenset())
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-AXIS unmapped boundary: b1",
    )


# --- REG-AXIS-006 unreviewed exclusion --------------------------------------------------
def test_reg_axis_006_unreviewed_exclusion_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    exclusions[0] = dataclasses.replace(exclusions[0], review_reference="   ")
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-AXIS unreviewed exclusion: e1",
    )


# --- REG-META-001 blank rationale -------------------------------------------------------
def test_reg_meta_001_blank_rationale_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(cases[0], rationale="   ")
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-META incomplete evidence: C1",
    )


# --- REG-META-002 incomplete evidence ---------------------------------------------------
def test_reg_meta_002_incomplete_evidence_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(cases[0], evidence_reference="")
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-META incomplete evidence: C1",
    )


# --- REG-META-003 missing implementing owner --------------------------------------------
def test_reg_meta_003_missing_owner_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(
        cases[0],
        classification=Classification.INTENTIONAL_CHANGE,
        target_owner=None,
        target_observation="new redacted stdout contract",
    )
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-META incomplete target: C1",
    )


# --- REG-META-004 incomplete intentional change -----------------------------------------
def test_reg_meta_004_incomplete_intentional_change_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(
        cases[0],
        classification=Classification.INTENTIONAL_CHANGE,
        target_owner="slice-2",
        target_observation=None,
    )
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-META incomplete target: C1",
    )


# --- REG-META-005 policy mismatch -------------------------------------------------------
def test_reg_meta_005_policy_mismatch_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(cases[0], surface_id="unlisted-surface")
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-META unknown surface: C1:unlisted-surface",
    )


def test_known_surface_policy_passes():
    cases, axes, boundaries, exclusions, _ = valid_registry()
    from tests.matrix.model import SurfaceClass

    policy = SurfacePolicy(
        surface_id="raw-json",
        surface_class=SurfaceClass.ADAPTER_PRIVATE,
        allowed_fields=frozenset(),
        forbidden_sentinels=frozenset(),
    )
    cases[0] = dataclasses.replace(cases[0], surface_id="raw-json")
    assert validate_registry(cases, axes, boundaries, exclusions, [policy]) == ()


# --- registry-level lane validation -----------------------------------------------------
def test_reg_lane_duplicate_context_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(cases[0], contexts=("csv", "csv"))
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-LANE duplicate context: C1",
    )


def test_reg_lane_missing_context_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(cases[0], contexts=())
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-LANE missing context: C1",
    )


def test_new_acceptance_with_contexts_is_rejected():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(
        cases[0],
        classification=Classification.NEW_ACCEPTANCE,
        target_owner="slice-3",
        target_observation="future acceptance placeholder",
    )
    # contexts still ("csv","xlsx") -> a future-acceptance row must not be executable.
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-LANE future acceptance is executable: C1",
    )


def test_new_acceptance_without_contexts_yields_no_execution_keys():
    case = make_case(
        classification=Classification.NEW_ACCEPTANCE,
        contexts=(),
        target_owner="slice-3",
        target_observation="placeholder",
    )
    assert case.execution_keys() == ()
    assert execution_keys([case], Lane.DEFAULT) == frozenset()


def test_reg_meta_unresolved_text_fails():
    cases, axes, boundaries, exclusions, policies = valid_registry()
    cases[0] = dataclasses.replace(cases[0], rationale="TODO wire this up")
    assert validate_registry(cases, axes, boundaries, exclusions, policies) == (
        "REG-META unresolved text: C1",
    )
