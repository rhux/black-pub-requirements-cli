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

# Acquisition-domain boundaries (Task 19): the browser-driven acquisition seams in
# scout_schedule_cli, plus the network-policy boundary created in Slice 1a. Each
# ``required_case_ids`` names acquisition-domain cases that drive the seam.
_ACQUISITION_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="ACQ-B-FORM-VALUES",
        qualified_name="scout_schedule_cli.form_values",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {"ACQ-ID-001", "ACQ-ID-002", "ACQ-ID-003", "ACQ-ID-004"}
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-IS-SCHEDULE-RESPONSE",
        qualified_name="scout_schedule_cli.is_schedule_response",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {"ACQ-RESP-001", "ACQ-RESP-002", "ACQ-RESP-003", "ACQ-RESP-004"}
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-NAVIGATE",
        qualified_name="scout_schedule_cli.navigate_and_trigger_schedule",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {"ACQ-RESP-001", "ACQ-SCHED-002", "ACQ-IDENTITY-001"}
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-POST-REQUIREMENT",
        qualified_name="scout_schedule_cli.post_requirement",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {
                "ACQ-REQ-001",
                "ACQ-REQ-002",
                "ACQ-REQ-003",
                "ACQ-REQ-004",
                "ACQ-REQ-005",
                "ACQ-REQ-006",
                "ACQ-RETRY-001",
                "ACQ-RETRY-002",
                "ACQ-RETRY-003",
                "ACQ-DELAY-001",
                "ACQ-DELAY-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-PROCESS-SCOUT",
        qualified_name="scout_schedule_cli.process_scout",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {
                "ACQ-SCHED-001",
                "ACQ-SCHED-002",
                "ACQ-SCHED-003",
                "ACQ-SCHED-004",
                "ACQ-SCHED-005",
                "ACQ-DEDUP-001",
                "ACQ-DEDUP-002",
                "ACQ-DEDUP-003",
                "ACQ-DEDUP-004",
                "ACQ-DEDUP-005",
                "ACQ-HASREQ-001",
                "ACQ-HASREQ-002",
                "ACQ-HASREQ-003",
                "ACQ-CLEAN-001",
                "ACQ-CLEAN-002",
                "ACQ-CLEAN-003",
                "ACQ-ASSET-001",
                "ACQ-ASSET-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-OUTPUT-ID",
        qualified_name="scout_schedule_cli.RunIdentity.output_id",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {
                "ACQ-RAW-001",
                "ACQ-RAW-002",
                "ACQ-RAW-003",
                "ACQ-IDENTITY-001",
                "ACQ-IDENTITY-002",
                "ACQ-IDENTITY-003",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-EGRESS",
        qualified_name="scoutmb.network_policy.assert_egress_allowed",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset(
            {"NET-POLICY-001", "NET-POLICY-002", "NET-POLICY-003"}
        ),
    ),
    BoundarySpec(
        boundary_id="ACQ-B-ASYNC-MAIN",
        qualified_name="scout_schedule_cli.async_main",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset({"ACQ-CLEAN-002", "ACQ-CLEAN-003"}),
    ),
)

# Requirement-domain boundaries (Task 20): the requirement-inference seams in
# scout_schedule_cli. Each ``required_case_ids`` names requirement-domain cases that drive
# the seam.
_REQUIREMENT_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="REQ-B-PATH",
        qualified_name="scout_schedule_cli.requirement_path",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset(
            {"REQ-SHAPE-001", "REQ-EMPTY-001", "REQ-EMPTY-002", "REQ-NOTE-001", "REQ-NOTE-002"}
        ),
    ),
    BoundarySpec(
        boundary_id="REQ-B-CHOICE",
        qualified_name="scout_schedule_cli.choice_requirement_count",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset({f"REQ-CHOICE-{i:03d}" for i in range(1, 31)}),
    ),
    BoundarySpec(
        boundary_id="REQ-B-ANNOTATE",
        qualified_name="scout_schedule_cli.annotate_requirement_statuses",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset(
            {
                "REQ-FLAG-001",
                "REQ-FLAG-005",
                "REQ-TYPE-001",
                "REQ-TREE-001",
                "REQ-TREE-002",
                "REQ-TREE-003",
                "REQ-TREE-004",
                "REQ-TREE-005",
                "REQ-TREE-006",
                "REQ-NONMUTATE-001",
                "REQ-NONMUTATE-002",
                "REQ-IDENTITY-001",
                "REQ-IDENTITY-002",
                "REQ-IDENTITY-003",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="REQ-B-MISSING",
        qualified_name="scout_schedule_cli.build_missing_requirements",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset({"REQ-EXCLUDE-001", "REQ-EXCLUDE-002"}),
    ),
    BoundarySpec(
        boundary_id="REQ-B-EMAIL-TEXT",
        qualified_name="scout_schedule_cli.render_email_text",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset({"REQ-SHAPE-001"}),
    ),
    BoundarySpec(
        boundary_id="REQ-B-EMAIL-HTML",
        qualified_name="scout_schedule_cli.render_email_html",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset({"REQ-SHAPE-001"}),
    ),
)

# Artifact-domain boundaries (Task 20): the output-writing and publication seams in
# scout_schedule_cli.
_ARTIFACT_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="ART-B-WRITE-OUTPUTS",
        qualified_name="scout_schedule_cli.write_outputs",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset(
            {
                "ART-SCHEMA-001",
                "ART-SCHEMA-002",
                "ART-SCHEMA-003",
                "ART-SCHEMA-004",
                "ART-SCHEMA-005",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="ART-B-HTML-REPORT",
        qualified_name="scout_schedule_cli.write_html_report",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset({"ART-SCHEMA-006"}),
    ),
    BoundarySpec(
        boundary_id="ART-B-EMAIL",
        qualified_name="scout_schedule_cli.write_email_reports",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset(
            {
                "ART-SCHEMA-007",
                "ART-SCHEMA-008",
                "ART-EMAIL-001",
                "ART-EMAIL-002",
                "ART-EMAIL-003",
                "ART-EMAIL-004",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="ART-B-JSON-FOR-HTML",
        qualified_name="scout_schedule_cli.json_for_html",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset(
            {
                "ART-HTML-001",
                "ART-HTML-002",
                "ART-HTML-003",
                "ART-HTML-004",
                "ART-HTML-005",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="ART-B-FILENAME",
        qualified_name="scout_schedule_cli.attendee_filename_stem",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset({f"ART-NAME-{i:03d}" for i in range(1, 10)}),
    ),
    BoundarySpec(
        boundary_id="ART-B-WRITE-CSV",
        qualified_name="scout_schedule_cli.write_csv",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset({f"ART-FORMULA-{i:03d}" for i in range(1, 7)}),
    ),
    BoundarySpec(
        boundary_id="ART-B-ATOMIC-WRITE",
        qualified_name="scout_schedule_cli.atomic_write_text",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset({f"ART-FAIL-{i:03d}" for i in range(1, 7)}),
    ),
)

# Platform-domain boundaries (Task 21): the single real path-sanitization seam these pure
# Windows/macOS-shaped cases drive.
_PLATFORM_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="PLAT-B-SLUG",
        qualified_name="scout_schedule_cli.safe_slug",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset(
            {f"PLAT-WIN-{i:03d}" for i in range(1, 9)}
            | {f"PLAT-MAC-{i:03d}" for i in range(1, 6)}
        ),
    ),
)

# Interface-domain boundaries (Task 21): the ui.server import-time seam, its 12 live routes, the
# run-id path-safety guard, and the run-listing seam.
_INTERFACE_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="UI-B-IMPORT",
        qualified_name="ui.server (module import)",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset({"UI-IMPORT-001", "UI-IMPORT-002"}),
    ),
    BoundarySpec(
        boundary_id="UI-B-ROUTES",
        qualified_name="ui.server.app (FastAPI route table)",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset(
            {f"UI-METHOD-{i:03d}" for i in range(1, 13)}
            | {f"UI-ROUTE-{i:03d}" for i in range(1, 24)}
        ),
    ),
    BoundarySpec(
        boundary_id="UI-B-SAFE-RUN-ID",
        qualified_name="ui.server._safe_run_id",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset({f"RUN-ID-{i:03d}" for i in range(1, 5)}),
    ),
    BoundarySpec(
        boundary_id="UI-B-LIST-RUNS",
        qualified_name="ui.server.list_runs",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset({f"RUN-LIST-{i:03d}" for i in range(1, 5)}),
    ),
)

# Populated by later slices; Task 17 adds the input-domain load_* seams, Task 18 the PDF seams,
# Task 19 the acquisition + network-policy seams, Task 20 the requirement + artifact seams,
# Task 21 the platform seam + the interface (ui.server) seams.
BOUNDARIES: tuple[BoundarySpec, ...] = (
    _INPUT_BOUNDARIES
    + _PDF_BOUNDARIES
    + _ACQUISITION_BOUNDARIES
    + _REQUIREMENT_BOUNDARIES
    + _ARTIFACT_BOUNDARIES
    + _PLATFORM_BOUNDARIES
    + _INTERFACE_BOUNDARIES
)
EXCLUSIONS: tuple[BranchExclusion, ...] = ()
COVERAGE_AREAS: tuple[CoverageAreaSpec, ...] = ()
