from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import Domain


@dataclass(frozen=True, slots=True)
class BoundarySpec:
    boundary_id: str
    qualified_name: str
    domain: Domain
    required_case_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class BranchExclusion:
    exclusion_id: str
    area_id: str
    file: str
    line: int
    branch_to: int | None
    rationale: str
    review_reference: str


@dataclass(frozen=True, slots=True)
class CoverageAreaSpec:
    area_id: str
    files: tuple[str, ...]


# Populated by later slices; Task 16 ships the types only.
BOUNDARIES: tuple[BoundarySpec, ...] = ()
EXCLUSIONS: tuple[BranchExclusion, ...] = ()
COVERAGE_AREAS: tuple[CoverageAreaSpec, ...] = ()
