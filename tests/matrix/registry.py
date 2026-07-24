from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from tests.matrix.axes import AxisSpec
from tests.matrix.boundaries import BoundarySpec, BranchExclusion
from tests.matrix.model import CaseMetadata, Classification, ExecutionKey, Lane
from tests.matrix.policies import SurfacePolicy

# Terms are split with "+" concatenation so the literal placeholder substrings never appear
# in this file's own source — otherwise the metadata-scanning gate that consumes this list
# would flag registry.py itself as containing a forbidden term.
_FORBIDDEN_METADATA_TERMS = (
    "t" + "bd",
    "t" + "odo",
    "implement " + "later",
    "optionally " + "extend",
    "represen" + "tative",
)


def execution_keys(cases: Iterable[CaseMetadata], lane: Lane) -> frozenset[ExecutionKey]:
    return frozenset(key for case in cases if case.lane is lane for key in case.execution_keys())


def _validate_ids(cases: Sequence[CaseMetadata]) -> list[str]:
    case_ids = [case.case_id for case in cases]
    duplicate_ids = sorted(cid for cid, count in Counter(case_ids).items() if count > 1)
    return [f"REG-ID duplicate case: {cid}" for cid in duplicate_ids]


def _validate_metadata(
    cases: Sequence[CaseMetadata],
    axes: Sequence[AxisSpec],
    policies: Sequence[SurfacePolicy],
) -> list[str]:
    errors: list[str] = []
    axis_by_id = {axis.axis_id: axis for axis in axes}
    policy_ids = {policy.surface_id for policy in policies}
    for case in cases:
        axis = axis_by_id.get(case.axis_id)
        if axis is None:
            errors.append(f"REG-AXIS unknown axis: {case.case_id}:{case.axis_id}")
            continue
        if case.member not in axis.members:
            errors.append(f"REG-AXIS unknown member: {case.case_id}:{case.member}")
        if not case.rationale.strip() or not case.evidence_reference.strip():
            errors.append(f"REG-META incomplete evidence: {case.case_id}")
        metadata_text = " ".join(
            (case.rationale, case.evidence_reference, case.target_observation or "")
        ).casefold()
        if any(term in metadata_text for term in _FORBIDDEN_METADATA_TERMS):
            errors.append(f"REG-META unresolved text: {case.case_id}")
        needs_target = case.classification is not Classification.PRESERVE
        if needs_target and (not case.target_owner or not case.target_observation):
            errors.append(f"REG-META incomplete target: {case.case_id}")
        if case.surface_id is not None and case.surface_id not in policy_ids:
            errors.append(f"REG-META unknown surface: {case.case_id}:{case.surface_id}")
        if len(case.contexts) != len(set(case.contexts)):
            errors.append(f"REG-LANE duplicate context: {case.case_id}")
        if case.classification is Classification.NEW_ACCEPTANCE and case.contexts:
            errors.append(f"REG-LANE future acceptance is executable: {case.case_id}")
        if case.classification is not Classification.NEW_ACCEPTANCE and not case.contexts:
            errors.append(f"REG-LANE missing context: {case.case_id}")
    return errors


def _validate_axes(
    cases: Sequence[CaseMetadata],
    axes: Sequence[AxisSpec],
    boundaries: Sequence[BoundarySpec],
) -> list[str]:
    errors: list[str] = []
    boundary_by_id = {boundary.boundary_id: boundary for boundary in boundaries}
    for axis in axes:
        axis_cases = [case for case in cases if case.axis_id == axis.axis_id]
        observed_members = {case.member for case in axis_cases}
        for member in sorted(axis.members - observed_members):
            errors.append(f"REG-AXIS missing member: {axis.axis_id}:{member}")
        if len(axis_cases) < axis.min_focused_cases:
            errors.append(f"REG-AXIS too few cases: {axis.axis_id}")
        observed_interactions: frozenset[str] = frozenset().union(
            *(case.interaction_ids for case in axis_cases)
        )
        for interaction in sorted(axis.interactions - observed_interactions):
            errors.append(f"REG-AXIS missing interaction: {axis.axis_id}:{interaction}")
        for boundary_id in sorted(axis.boundaries - boundary_by_id.keys()):
            errors.append(f"REG-AXIS unknown boundary: {axis.axis_id}:{boundary_id}")
    return errors


def _validate_boundaries(
    cases: Sequence[CaseMetadata],
    boundaries: Sequence[BoundarySpec],
) -> list[str]:
    errors: list[str] = []
    case_by_id = {case.case_id: case for case in cases}
    for boundary in boundaries:
        if not boundary.required_case_ids:
            errors.append(f"REG-AXIS unmapped boundary: {boundary.boundary_id}")
        for case_id in sorted(boundary.required_case_ids - case_by_id.keys()):
            errors.append(f"REG-AXIS unmapped boundary: {boundary.boundary_id}:{case_id}")
        for case_id in sorted(boundary.required_case_ids & case_by_id.keys()):
            if case_by_id[case_id].domain is not boundary.domain:
                errors.append(
                    f"REG-AXIS boundary domain mismatch: {boundary.boundary_id}:{case_id}"
                )
    return errors


def _validate_policies(exclusions: Sequence[BranchExclusion]) -> list[str]:
    errors: list[str] = []
    for exclusion in exclusions:
        if not exclusion.rationale.strip() or not exclusion.review_reference.strip():
            errors.append(f"REG-AXIS unreviewed exclusion: {exclusion.exclusion_id}")
    return errors


def validate_registry(
    cases: Sequence[CaseMetadata],
    axes: Sequence[AxisSpec],
    boundaries: Sequence[BoundarySpec],
    exclusions: Sequence[BranchExclusion],
    policies: Sequence[SurfacePolicy],
) -> tuple[str, ...]:
    errors: list[str] = []
    errors += _validate_ids(cases)
    errors += _validate_metadata(cases, axes, policies)
    errors += _validate_axes(cases, axes, boundaries)
    errors += _validate_boundaries(cases, boundaries)
    errors += _validate_policies(exclusions)
    return tuple(sorted(errors))
