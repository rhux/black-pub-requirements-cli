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

# PDF-domain boundaries (Task 18): the extraction and CLI seams in pdf_to_scouts. Each
# ``required_case_ids`` names PDF-domain cases that drive the seam.
_PDF_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="PDF-B-EXPAND",
        qualified_name="pdf_to_scouts.expand_pdf_inputs",
        domain=Domain.PDF,
        required_case_ids=frozenset(
            {
                "PDF-DISC-001",
                "PDF-DISC-002",
                "PDF-DISC-003",
                "PDF-DISC-004",
                "PDF-DISC-005",
                "PDF-DISC-006",
                "PDF-CLI-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="PDF-B-IDENTITY",
        qualified_name="pdf_to_scouts.extract_page_identity",
        domain=Domain.PDF,
        required_case_ids=frozenset(
            {
                "PDF-ID-001",
                "PDF-ID-002",
                "PDF-ID-003",
                "PDF-ID-004",
                "PDF-ID-005",
                "PDF-ID-006",
                "PDF-ID-007",
                "PDF-ID-008",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="PDF-B-NORMALIZE",
        qualified_name="pdf_to_scouts.normalize_obvious_case",
        domain=Domain.PDF,
        required_case_ids=frozenset(
            {"PDF-CASE-001", "PDF-CASE-002", "PDF-CASE-003", "PDF-CASE-004"}
        ),
    ),
    BoundarySpec(
        boundary_id="PDF-B-EMBEDDED",
        qualified_name="pdf_to_scouts.decode_embedded_qr",
        domain=Domain.PDF,
        required_case_ids=frozenset({"PDF-QR-001", "PDF-QR-003", "PDF-QR-005"}),
    ),
    BoundarySpec(
        boundary_id="PDF-B-RENDERED",
        qualified_name="pdf_to_scouts.decode_rendered_qr",
        domain=Domain.PDF,
        required_case_ids=frozenset(
            {"PDF-QR-002", "PDF-QR-006", "PDF-DEBUG-001", "PDF-DEBUG-002", "PDF-CORRUPT-002"}
        ),
    ),
    BoundarySpec(
        boundary_id="PDF-B-EXTRACT",
        qualified_name="pdf_to_scouts.extract_pdf",
        domain=Domain.PDF,
        required_case_ids=frozenset(
            {
                "PDF-ID-001",
                "PDF-PAGE-001",
                "PDF-PAGE-002",
                "PDF-CORRUPT-001",
                "PDF-CORRUPT-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="PDF-B-ATTENDEE-CSV",
        qualified_name="pdf_to_scouts.write_attendees_csv",
        domain=Domain.PDF,
        required_case_ids=frozenset({"PDF-SCHEMA-001", "PDF-FILTER-001"}),
    ),
    BoundarySpec(
        boundary_id="PDF-B-ERRORS-CSV",
        qualified_name="pdf_to_scouts.write_errors_csv",
        domain=Domain.PDF,
        required_case_ids=frozenset({"PDF-SCHEMA-002", "PDF-CLI-006"}),
    ),
    BoundarySpec(
        boundary_id="PDF-B-MAIN",
        qualified_name="pdf_to_scouts.main",
        domain=Domain.PDF,
        required_case_ids=frozenset({"PDF-CLI-005", "PDF-CLI-007", "PDF-FILTER-003"}),
    ),
)

# Populated by later slices; Task 17 adds the input-domain load_* seams, Task 18 the PDF seams.
BOUNDARIES: tuple[BoundarySpec, ...] = _INPUT_BOUNDARIES + _PDF_BOUNDARIES
EXCLUSIONS: tuple[BranchExclusion, ...] = ()
COVERAGE_AREAS: tuple[CoverageAreaSpec, ...] = ()
