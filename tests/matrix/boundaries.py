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


# Input-domain boundaries (Task 17): the load_* seams in scout_schedule_cli. Each
# ``required_case_ids`` names input-domain cases that drive the seam.
_INPUT_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="IN-B-LOAD-INPUTS",
        qualified_name="scout_schedule_cli.load_inputs",
        domain=Domain.INPUT,
        required_case_ids=frozenset(
            {
                "IN-FILTER-001",
                "IN-FILTER-002",
                "IN-FILTER-003",
                "IN-FILTER-004",
                "IN-FILTER-005",
                "IN-FILTER-006",
                "IN-DEDUP-001",
                "IN-DEDUP-002",
                "IN-EMPTY-001",
                "IN-EMPTY-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="IN-B-LOAD-CSV",
        qualified_name="scout_schedule_cli.load_csv",
        domain=Domain.INPUT,
        required_case_ids=frozenset(
            {
                "IN-FORMAT-001",
                "IN-ALIAS-NAME-001",
                "IN-ALIAS-URL-001",
                "IN-ALIAS-TYPE-001",
                "IN-HEADER-001",
                "IN-HEADER-002",
                "IN-HEADER-003",
                "IN-HEADER-004",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="IN-B-LOAD-XLSX",
        qualified_name="scout_schedule_cli.load_xlsx",
        domain=Domain.INPUT,
        required_case_ids=frozenset(
            {
                "IN-FORMAT-002",
                "IN-XLSX-SHEET-001",
                "IN-XLSX-SHEET-002",
                "IN-XLSX-SHEET-003",
                "IN-XLSX-ERR-001",
                "IN-XLSX-ERR-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="IN-B-LOAD-JSON",
        qualified_name="scout_schedule_cli.load_json",
        domain=Domain.INPUT,
        required_case_ids=frozenset(
            {
                "IN-FORMAT-003",
                "IN-FORMAT-004",
                "IN-FORMAT-005",
                "IN-FORMAT-006",
                "IN-FORMAT-007",
                "IN-JSON-001",
                "IN-JSON-002",
                "IN-JSON-003",
                "IN-JSON-004",
                "IN-JSON-005",
                "IN-JSON-006",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="IN-B-LOAD-TEXT",
        qualified_name="scout_schedule_cli.load_text",
        domain=Domain.INPUT,
        required_case_ids=frozenset(
            {
                "IN-FORMAT-008",
                "IN-TEXT-001",
                "IN-TEXT-002",
                "IN-TEXT-003",
                "IN-TEXT-004",
            }
        ),
    ),
)

# Populated by later slices; Task 17 adds the input-domain load_* seams.
BOUNDARIES: tuple[BoundarySpec, ...] = _INPUT_BOUNDARIES
EXCLUSIONS: tuple[BranchExclusion, ...] = ()
COVERAGE_AREAS: tuple[CoverageAreaSpec, ...] = ()
