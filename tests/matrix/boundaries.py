from __future__ import annotations

from dataclasses import dataclass

from tests.matrix.model import Domain


@dataclass(frozen=True, slots=True)
class BoundarySpec:
    boundary_id: str
    qualified_name: str
    domain: Domain
    required_case_ids: frozenset[str]
    # Task 24: the package-side seam that now carries the SAME behavior as ``qualified_name``
    # (which stays pointed at the legacy flat module -- often a re-export shim as of 2a). Left
    # "" for boundaries with no package-side counterpart yet.
    package_qualified_name: str = ""


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


# Corpus-domain boundaries (Task 16 backfill, Slice 1b Phase A Gate): the tools/verify_corpus.py
# and tests/harnesses/corpus.py seams the CORP-* cases drive. The REG-* rows (registry
# self-tests) are NEW_ACCEPTANCE with contexts=() and are not mapped to any boundary here --
# see tests/matrix/cases/corpus_cases.py's module docstring.
_CORPUS_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="CORP-B-CLASSIFY",
        qualified_name="tools.verify_corpus.classify_row",
        domain=Domain.CORPUS,
        required_case_ids=frozenset(
            {"CORP-SPLIT-001", "CORP-SPLIT-002", "CORP-SPLIT-003", "CORP-SPLIT-004"}
        ),
    ),
    BoundarySpec(
        boundary_id="CORP-B-SUMMARIZE",
        qualified_name="tools.verify_corpus.summarize_run",
        domain=Domain.CORPUS,
        required_case_ids=frozenset({"CORP-SPLIT-001", "CORP-CANON-001"}),
    ),
    BoundarySpec(
        boundary_id="CORP-B-MAIN",
        qualified_name="tools.verify_corpus.main",
        domain=Domain.CORPUS,
        required_case_ids=frozenset({"CORP-CLI-001", "CORP-CLI-002"}),
    ),
    BoundarySpec(
        boundary_id="CORP-B-FINGERPRINT",
        qualified_name="tests.harnesses.corpus.fingerprint_tree",
        domain=Domain.CORPUS,
        required_case_ids=frozenset(
            {
                "CORP-FP-001",
                "CORP-FP-002",
                "CORP-FP-003",
                "CORP-FP-004",
                "CORP-READ-001",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="CORP-B-CORPUS-STATUS",
        qualified_name="tests.harnesses.corpus.corpus_status",
        domain=Domain.CORPUS,
        required_case_ids=frozenset(
            {"CORP-MODE-001", "CORP-MODE-002", "CORP-MODE-003", "CORP-MODE-004"}
        ),
    ),
    BoundarySpec(
        boundary_id="CORP-B-MULTISET",
        qualified_name="tests.harnesses.corpus.raw_payload_multiset / raw_multisets_all_match",
        domain=Domain.CORPUS,
        required_case_ids=frozenset({"CORP-SNAPSHOT-001", "CORP-SNAPSHOT-002"}),
    ),
    BoundarySpec(
        boundary_id="CORP-B-PDF-AGGREGATE",
        qualified_name="tests.harnesses.corpus.extract_pdf_aggregate",
        domain=Domain.CORPUS,
        required_case_ids=frozenset({"CORP-PDF-001"}),
    ),
)

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
        package_qualified_name="scoutmb.adapters.files.tabular.TabularAttendeeSource.load",
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
        package_qualified_name="scoutmb.adapters.files.tabular.load_csv",
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
        package_qualified_name="scoutmb.adapters.files.tabular.load_xlsx",
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
        package_qualified_name="scoutmb.adapters.files.tabular.load_json",
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
        package_qualified_name="scoutmb.adapters.files.tabular.load_text",
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
        required_case_ids=frozenset({"ACQ-ID-001", "ACQ-ID-002", "ACQ-ID-003", "ACQ-ID-004"}),
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
        required_case_ids=frozenset({"ACQ-RESP-001", "ACQ-SCHED-002", "ACQ-IDENTITY-001"}),
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
        package_qualified_name="scoutmb.core.identity.RunIdentity.output_id",
    ),
    BoundarySpec(
        boundary_id="ACQ-B-EGRESS",
        qualified_name="scoutmb.network_policy.assert_egress_allowed",
        domain=Domain.ACQUISITION,
        required_case_ids=frozenset({"NET-POLICY-001", "NET-POLICY-002", "NET-POLICY-003"}),
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
        package_qualified_name="scoutmb.core.inference.numbering.requirement_path",
    ),
    BoundarySpec(
        boundary_id="REQ-B-CHOICE",
        qualified_name="scout_schedule_cli.choice_requirement_count",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset({f"REQ-CHOICE-{i:03d}" for i in range(1, 31)}),
        package_qualified_name="scoutmb.core.inference.numbering.choice_requirement_count",
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
        package_qualified_name="scoutmb.core.inference.status.calculate_statuses",
    ),
    BoundarySpec(
        boundary_id="REQ-B-MISSING",
        qualified_name="scout_schedule_cli.build_missing_requirements",
        domain=Domain.REQUIREMENT,
        required_case_ids=frozenset({"REQ-EXCLUDE-001", "REQ-EXCLUDE-002"}),
        package_qualified_name="scoutmb.core.inference.missing.select_actionable",
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
        package_qualified_name="scoutmb.core.output_schemas.json_for_html",
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
        package_qualified_name="scoutmb.adapters.files.atomic.write_csv",
    ),
    BoundarySpec(
        boundary_id="ART-B-ATOMIC-WRITE",
        qualified_name="scout_schedule_cli.atomic_write_text",
        domain=Domain.ARTIFACT,
        required_case_ids=frozenset({f"ART-FAIL-{i:03d}" for i in range(1, 7)}),
        package_qualified_name="scoutmb.adapters.files.atomic.atomic_write_text",
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
            {f"PLAT-WIN-{i:03d}" for i in range(1, 9)} | {f"PLAT-MAC-{i:03d}" for i in range(1, 6)}
        ),
        package_qualified_name="scoutmb.core.identity.safe_slug",
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
            | {f"UI-ROUTE-{i:03d}" for i in range(1, 31)}
        ),
    ),
    BoundarySpec(
        boundary_id="SSE-B-FRAMES",
        qualified_name="ui.server.operation_events.event_stream",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset({f"SSE-FRAME-{i:03d}" for i in range(1, 7)}),
    ),
    BoundarySpec(
        boundary_id="SSE-B-CLEANUP",
        qualified_name="ui.server.operation_events / worker (lifecycle cleanup)",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset({f"SSE-CLEAN-{i:03d}" for i in range(1, 5)}),
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
    BoundarySpec(
        boundary_id="CLI-B-MAIN",
        qualified_name="scout_schedule_cli.main",
        domain=Domain.INTERFACE,
        required_case_ids=frozenset({f"CLI-SCHED-{i:03d}" for i in range(1, 7)}),
    ),
)

# Desktop-launcher boundaries (Task 21, final slice): run_app.py's three seams.
_DESKTOP_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="DESK-B-PORT",
        qualified_name="run_app.free_port",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset({"DESK-PORT-001", "DESK-PORT-002"}),
    ),
    BoundarySpec(
        boundary_id="DESK-B-READY",
        qualified_name="run_app.wait_until_ready",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset({f"DESK-READY-{i:03d}" for i in range(1, 4)}),
    ),
    BoundarySpec(
        boundary_id="DESK-B-MODE",
        qualified_name="run_app.main",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset({f"DESK-MODE-{i:03d}" for i in range(1, 5)}),
    ),
)

# Bootstrap boundaries (Task 21, final slice): bootstrap/paths.py, marker.py, source_sync.py.
_BOOTSTRAP_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="BOOT-B-PATH",
        qualified_name="bootstrap.paths.resolve_root",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset({f"BOOT-PATH-{i:03d}" for i in range(1, 5)}),
    ),
    BoundarySpec(
        boundary_id="BOOT-B-MARKER",
        qualified_name="bootstrap.marker.is_environment_valid",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset({f"BOOT-MARK-{i:03d}" for i in range(1, 7)}),
    ),
    BoundarySpec(
        boundary_id="BOOT-B-SYNC",
        qualified_name="bootstrap.source_sync.sync_app_source",
        domain=Domain.PLATFORM,
        required_case_ids=frozenset({f"BOOT-SYNC-{i:03d}" for i in range(1, 5)}),
    ),
)

# Scale-profile boundaries (Task 22, Slice 1b Phase A): the synthetic-data generation seams in
# tests/matrix/scale_profile.py and tests/factories/scale.py.
_SCALE_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="SCALE-B-BUILD-DATASET",
        qualified_name="tests.factories.scale.build_dataset",
        domain=Domain.SCALE,
        required_case_ids=frozenset(
            {
                "SCALE-000",
                "SCALE-001",
                "SCALE-002",
                "SCALE-SMALL-001",
                "SCALE-SMALL-002",
                "SCALE-SMALL-003",
                "SCALE-CANON-022",
                "SCALE-LARGE-050",
                "SCALE-PROP-001",
                "SCALE-PROP-002",
            }
        ),
    ),
    BoundarySpec(
        boundary_id="SCALE-B-PAIRING",
        qualified_name="tests.matrix.scale_profile.pairing_order / require_supported",
        domain=Domain.SCALE,
        required_case_ids=frozenset({"SCALE-PAIR-001", "SCALE-PAIR-002"}),
    ),
)

# Vertical-flow and performance-baseline boundaries (Task 22, Slice 1b Phase A): the real
# 5-stage end-to-end pipeline and the request-count/growth-bound instrumentation seams.
_FLOW_BOUNDARIES: tuple[BoundarySpec, ...] = (
    BoundarySpec(
        boundary_id="FLOW-B-END-TO-END",
        qualified_name="pdf_to_scouts.extract_pdf -> scout_schedule_cli.process_scout -> "
        "write_outputs -> ui.server (read routes)",
        domain=Domain.FLOW,
        required_case_ids=frozenset({"FLOW-SUCCESS-001", "FLOW-PARTIAL-001"}),
    ),
    BoundarySpec(
        boundary_id="FLOW-B-REQUEST-COUNT",
        qualified_name="scout_schedule_cli.process_scout (request sequence)",
        domain=Domain.FLOW,
        required_case_ids=frozenset({"PERF-REQ-001", "PERF-REQ-002", "PERF-REQ-003"}),
    ),
    BoundarySpec(
        boundary_id="FLOW-B-GROWTH",
        qualified_name="scout_schedule_cli.annotate_requirement_statuses / write_outputs",
        domain=Domain.FLOW,
        required_case_ids=frozenset({"PERF-GROWTH-001", "PERF-GROWTH-002"}),
    ),
)

# Populated by later slices; Task 17 adds the input-domain load_* seams, Task 18 the PDF seams,
# Task 19 the acquisition + network-policy seams, Task 20 the requirement + artifact seams,
# Task 21 the platform seam + the interface (ui.server) seams + the desktop-launcher and
# bootstrap seams, Task 22 the scale-profile and vertical-flow/performance seams (final slice).
BOUNDARIES: tuple[BoundarySpec, ...] = (
    _CORPUS_BOUNDARIES
    + _INPUT_BOUNDARIES
    + _PDF_BOUNDARIES
    + _ACQUISITION_BOUNDARIES
    + _REQUIREMENT_BOUNDARIES
    + _ARTIFACT_BOUNDARIES
    + _PLATFORM_BOUNDARIES
    + _INTERFACE_BOUNDARIES
    + _DESKTOP_BOUNDARIES
    + _BOOTSTRAP_BOUNDARIES
    + _SCALE_BOUNDARIES
    + _FLOW_BOUNDARIES
)
# Scoped coverage areas (Task 22, step 8): the 5 production surfaces Phase A characterizes.
COVERAGE_AREAS: tuple[CoverageAreaSpec, ...] = (
    CoverageAreaSpec("schedule", ("scout_schedule_cli.py",)),
    CoverageAreaSpec("pdf", ("pdf_to_scouts.py",)),
    CoverageAreaSpec("ui", ("ui/server.py",)),
    CoverageAreaSpec("desktop", ("run_app.py",)),
    CoverageAreaSpec(
        "bootstrap",
        ("bootstrap/paths.py", "bootstrap/marker.py", "bootstrap/source_sync.py"),
    ),
    # Package-side coverage areas (Task 24): the scoutmb/ modules Tasks 1-23 moved real
    # behavior into. Floors are D10: core/ports >=95% branch, adapters/features >=90% branch.
    # ``files`` are exact coverage-JSON keys (tools/check_phase_a_coverage.py:79/:116), not
    # globs -- see tests/matrix/test_coverage_areas.py for the tripwire that keeps this list
    # honest as new package modules land. Empty __init__.py files are excluded: they have no
    # statements, so coverage.py omits them from the report entirely.
    CoverageAreaSpec(
        area_id="pkg-core",
        files=(
            "src/scoutmb/core/models.py",
            "src/scoutmb/core/identity.py",
            "src/scoutmb/core/output_schemas.py",
            "src/scoutmb/core/inference/numbering.py",
            "src/scoutmb/core/inference/tree.py",
            "src/scoutmb/core/inference/status.py",
            "src/scoutmb/core/inference/missing.py",
            "src/scoutmb/core/run_state.py",
        ),
    ),
    CoverageAreaSpec(
        area_id="pkg-ports",
        files=(
            "src/scoutmb/ports/clock.py",
            "src/scoutmb/ports/ids.py",
            "src/scoutmb/ports/attendee_source.py",
            "src/scoutmb/ports/artifact_sink.py",
            "src/scoutmb/ports/scoutevent.py",
            "src/scoutmb/ports/checkpoint_store.py",
        ),
    ),
    CoverageAreaSpec(
        area_id="pkg-adapters",
        files=(
            "src/scoutmb/adapters/files/atomic.py",
            "src/scoutmb/adapters/files/tabular.py",
            "src/scoutmb/adapters/pdf/extract.py",
            "src/scoutmb/adapters/pdf/pages.py",
            "src/scoutmb/adapters/html/report.py",
            "src/scoutmb/adapters/scoutevent/playwright_gateway.py",
            "src/scoutmb/adapters/scoutevent/http_gateway.py",
            "src/scoutmb/adapters/scoutevent/schema.py",
            "src/scoutmb/adapters/files/checkpoint.py",
        ),
    ),
    CoverageAreaSpec(
        area_id="pkg-features",
        files=(
            "src/scoutmb/features/ingest/service.py",
            "src/scoutmb/features/ingest/pdf_extract.py",
            "src/scoutmb/features/reporting/service.py",
            "src/scoutmb/features/acquisition/retry.py",
            "src/scoutmb/features/acquisition/service.py",
            "src/scoutmb/features/acquisition/batch.py",
            "src/scoutmb/features/acquisition/pipeline.py",
        ),
    ),
)

# Reviewed, narrowly-scoped exclusions (Task 22, step 9). Every entry here was left uncovered
# ONLY after a genuine attempt to close it with a real test (see
# tests/characterization/test_phase_a_gap_closure.py, which closed every other gap real
# coverage --branch turned up in these 5 files). Each entry is one exact line or one exact
# branch arc -- never a range -- with an honest reason it cannot reasonably be exercised from
# this test suite.
EXCLUSIONS: tuple[BranchExclusion, ...] = (
    # --- `if __name__ == "__main__": raise SystemExit(main())` entry-point guards. The `if`
    # line itself is always executed (and covered) at import time; only the body -- reachable
    # solely when the module is run as a script, never when pytest imports it -- is missing.
    BranchExclusion(
        exclusion_id="EXC-MAIN-GUARD-SCHEDULE-STMT",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=907,
        branch_to=None,
        rationale=(
            '`raise SystemExit(main())` under `if __name__ == "__main__":` only runs when '
            "the module is executed as a script; pytest always imports it as a module, so "
            '__name__ is never "__main__" during the test suite.'
        ),
        review_reference=(
            "Task 22 step 9 review: entry-point guard, structurally unreachable under pytest. "
            "Task 24 re-pin: line drifted from 1889 to 908 as Tasks 5-23 moved code out of "
            "scout_schedule_cli.py into the package; re-verified against the current file."
            "Fix-wave re-pin: line drifted from 908 to 907 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them)."
        ),
    ),
    BranchExclusion(
        exclusion_id="EXC-MAIN-GUARD-SCHEDULE-BRANCH",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=906,
        branch_to=907,
        rationale=(
            'The `if __name__ == "__main__":` true-branch arc to its body is never taken '
            "for the same reason as EXC-MAIN-GUARD-SCHEDULE-STMT."
        ),
        review_reference=(
            "Task 22 step 9 review: entry-point guard, structurally unreachable under pytest. "
            "Task 24 re-pin: line drifted from 1888->1889 to 907->908 as Tasks 5-23 moved code "
            "out of scout_schedule_cli.py into the package; re-verified against the current file."
            "Fix-wave re-pin: line drifted from 907->908 to 906->907 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them)."
        ),
    ),
    # EXC-MAIN-GUARD-PDF-STMT / EXC-MAIN-GUARD-PDF-BRANCH removed (Task 24 re-pin review):
    # pdf_to_scouts.py's `if __name__ == "__main__":` guard used to be structurally unreachable
    # under pytest, like its schedule/desktop siblings below -- but fixing the pytest-cov
    # subprocess-coverage-combining bug uncovered by this same re-pin (see pyproject.toml's
    # `--cov-branch` addopts entry) revealed that tests/compat/test_legacy_entrypoints.py's
    # `subprocess.run([sys.executable, "pdf_to_scouts.py", "--help"])` genuinely executes this
    # module as `__main__` and previously had its coverage silently discarded by a crashed
    # `coverage combine`. Verified directly against coverage.json: pdf_to_scouts.py is 11/11
    # statements, 2/2 branches with no exclusion needed. Kept as a stale-exclusion tripwire
    # example in the Task 24 report rather than re-added.
    BranchExclusion(
        exclusion_id="EXC-MAIN-GUARD-DESKTOP-STMT",
        area_id="desktop",
        file="run_app.py",
        line=89,
        branch_to=None,
        rationale=(
            '`raise SystemExit(main())` under `if __name__ == "__main__":` only runs when '
            "the module is executed as a script; pytest always imports it as a module."
        ),
        review_reference="Task 22 step 9 review: entry-point guard, structurally unreachable under pytest.",
    ),
    BranchExclusion(
        exclusion_id="EXC-MAIN-GUARD-DESKTOP-BRANCH",
        area_id="desktop",
        file="run_app.py",
        line=88,
        branch_to=89,
        rationale=(
            'The `if __name__ == "__main__":` true-branch arc to its body is never taken '
            "for the same reason as EXC-MAIN-GUARD-DESKTOP-STMT."
        ),
        review_reference="Task 22 step 9 review: entry-point guard, structurally unreachable under pytest.",
    ),
    # --- expand_pdf_inputs's Windows-glob fallback: the `for match in matches:` loop only
    # returns to its own top (rather than falling into the if/elif bodies) for a glob match that
    # is NEITHER a file NOR a directory -- e.g. a broken symlink, or a path deleted between
    # glob.glob() and the is_file()/is_dir() checks. Constructing that portably (broken symlinks
    # need elevated privileges to create on Windows, which this project also targets) would
    # trade a real, meaningful test for a platform-fragile one; a genuine TOCTOU race is not
    # something a deterministic unit test should simulate by deleting the path mid-call.
    #
    # Task 24 re-pin: the real implementation moved from pdf_to_scouts.py:157-161 into
    # scoutmb.features.ingest.pdf_extract.expand_pdf_inputs (Task 18); pdf_to_scouts.py itself
    # is now a 59-line re-export shim with no such loop, so the old file/line no longer resolves
    # to anything -- relocated to the package module and its area, same defensive branch.
    BranchExclusion(
        exclusion_id="EXC-PDF-GLOB-NEITHER-FILE-NOR-DIR",
        area_id="pkg-features",
        file="src/scoutmb/features/ingest/pdf_extract.py",
        line=53,
        branch_to=49,
        rationale=(
            "Only reached when a glob match is neither a file nor a directory (a broken "
            "symlink or a TOCTOU race between glob() and the is_file()/is_dir() checks). "
            "Constructing a broken symlink requires elevated privileges on Windows, which "
            "this project also targets, and simulating the race would require deleting the "
            "path mid-call rather than exercising real behavior."
        ),
        review_reference=(
            "Task 22 step 9 review: defensive branch, not portably testable across Windows+"
            "macOS. Task 24 re-pin: relocated from pdf_to_scouts.py:157-161 to "
            "scoutmb.features.ingest.pdf_extract.expand_pdf_inputs:49-53 (Task 18 moved the "
            "implementation into the package); re-verified against the current file."
        ),
    ),
    # --- ui/server._platform_data_root's OS dispatch. The project's own test policy (see
    # tests/characterization/test_platform_matrix.py's docstring) never monkeypatches
    # sys.platform, so only the branch matching THIS host's real platform can execute in any
    # one CI run; the other two are exercised for real on their own OS's CI job.
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-WIN32-STMT-BASE",
        area_id="ui",
        file="ui/server.py",
        line=42,
        branch_to=None,
        rationale=(
            '`os.environ.get("LOCALAPPDATA")` inside the `sys.platform == "win32"` branch '
            "only runs on a real Windows host; this suite never monkeypatches sys.platform "
            "(tests/characterization/test_platform_matrix.py's documented policy)."
        ),
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-WIN32-STMT-IF",
        area_id="ui",
        file="ui/server.py",
        line=43,
        branch_to=None,
        rationale="Same win32-only branch as EXC-UI-PLATFORM-WIN32-STMT-BASE.",
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-WIN32-STMT-RETURN",
        area_id="ui",
        file="ui/server.py",
        line=44,
        branch_to=None,
        rationale="Same win32-only branch as EXC-UI-PLATFORM-WIN32-STMT-BASE.",
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-LINUX-FALLBACK-STMT",
        area_id="ui",
        file="ui/server.py",
        line=47,
        branch_to=None,
        rationale=(
            'The final `return Path.home() / ".local" / "share" / ...` fallback only '
            "executes when sys.platform is neither win32 nor darwin; this host is darwin, so "
            "the darwin branch returns first. Exercised for real on Linux CI."
        ),
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-BRANCH-ENTER-WIN32",
        area_id="ui",
        file="ui/server.py",
        line=41,
        branch_to=42,
        rationale="The win32-true arc of the platform dispatch; same reasoning as EXC-UI-PLATFORM-WIN32-STMT-BASE.",
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-BRANCH-LOCALAPPDATA-TRUE",
        area_id="ui",
        file="ui/server.py",
        line=43,
        branch_to=44,
        rationale="The win32-true inner arc; same reasoning as EXC-UI-PLATFORM-WIN32-STMT-BASE.",
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-BRANCH-LOCALAPPDATA-FALSE",
        area_id="ui",
        file="ui/server.py",
        line=43,
        branch_to=47,
        rationale=(
            "The win32-but-no-LOCALAPPDATA arc falling through to the final fallback; only "
            "reachable on a real Windows host with LOCALAPPDATA unset."
        ),
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    BranchExclusion(
        exclusion_id="EXC-UI-PLATFORM-BRANCH-DARWIN-FALSE",
        area_id="ui",
        file="ui/server.py",
        line=45,
        branch_to=47,
        rationale=(
            "The darwin-elif-false arc: on this host sys.platform IS darwin, so this arc "
            "(reached only when it is neither win32 nor darwin) never taken here; exercised "
            "for real on Linux CI."
        ),
        review_reference="Task 22 step 9 review: OS-dispatch branch, exercised for real on its own OS's CI job.",
    ),
    # --- ui.server.open_emails_folder's success path. Already pinned, not just excluded: see
    # UI-ROUTE-023 (tests/matrix/cases/interface_cases.py), an intentional_change case that
    # asserts the REAL current behavior on this host is an unhandled 500 (os.startfile does not
    # exist on non-Windows Python). :387's `return {"opened": True}` is therefore reachable only
    # on real Windows; Slice 2 owns making this route dispatch on sys.platform.
    BranchExclusion(
        exclusion_id="EXC-UI-OPEN-EMAILS-WINDOWS-ONLY",
        area_id="ui",
        file="ui/server.py",
        line=387,
        branch_to=None,
        rationale=(
            "os.startfile does not exist on macOS/Linux, so this line is only reachable on "
            "real Windows; UI-ROUTE-023 already pins the current (non-Windows) behavior as an "
            "unhandled 500, an intentional-change owned by Slice 2 (cross-platform folder-open)."
        ),
        review_reference="Task 22 step 9 review: see UI-ROUTE-023 in tests/matrix/cases/interface_cases.py.",
    ),
    # =========================================================================================
    # Task 24 review: gaps found while re-deriving the baseline for the first time since Task 22
    # made write_outputs a "Form-2 shim" delegating to ReportingService.publish, and since the
    # four pkg-* areas above were characterized for the first time. Reviewed the same way as
    # Task 22 step 9: a genuine attempt to close each one with a real test first; each entry
    # below records why that attempt did not close it.
    # =========================================================================================
    #
    # --- scout_schedule_cli.write_html_report and its helper
    # _assert_blank_identity_results_have_no_records are now entirely unreached. Before Task 22
    # (commit ef5dd77), write_outputs called write_html_report directly; write_outputs now
    # delegates the real report-composition/write path to ReportingService.publish (its own,
    # independently-tested equivalent logic -- see the pkg-features/service.py entries below),
    # and no test calls scout_schedule_cli.write_html_report directly (only write_email_reports,
    # a sibling function, is still exercised that way). A genuine attempt to close this by
    # calling write_html_report directly is deferred: this legacy copy is slated for retirement
    # together with the rest of tests/harnesses/legacy.py at the START of Slice 2b (see this
    # plan's "Deferred to Slice 2b" section), so a same-slice test investment here would be
    # thrown away almost immediately. Every statement and branch in the two functions'
    # (unreachable) bodies is listed individually, matching this table's one-line-or-arc
    # convention.
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-STMT-FOR",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=491,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); this is its dead helper's loop header.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 493 to 491 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-STMT-IF",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=492,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); this is its dead helper's identity check.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 494 to 492 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-STMT-CONTINUE",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=493,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); this is its dead helper's continue.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 495 to 493 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-STMT-RECORDS-IF",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=494,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); this is its dead helper's records check.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 496 to 494 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-STMT-RAISE",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=495,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); this is its dead helper's raise.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 497 to 495 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-BRANCH-NOENTRY",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=491,
        branch_to=-478,
        rationale="write_html_report is unreached (see section header); zero-entry exit of the dead helper's loop.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 493->-480 to 491->-478 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-BRANCH-ENTRY",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=491,
        branch_to=492,
        rationale="write_html_report is unreached (see section header); loop-entry arc of the dead helper.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 493->494 to 491->492 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-BRANCH-CONTINUE-TRUE",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=492,
        branch_to=493,
        rationale="write_html_report is unreached (see section header); identity-blank arc of the dead helper.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 494->495 to 492->493 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-BRANCH-CONTINUE-FALSE",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=492,
        branch_to=494,
        rationale="write_html_report is unreached (see section header); identity-present arc of the dead helper.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 494->496 to 492->494 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-BRANCH-NORECORDS",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=494,
        branch_to=491,
        rationale="write_html_report is unreached (see section header); no-records loop-back arc of the dead helper.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 496->493 to 494->491 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-BLANK-GUARD-BRANCH-HASRECORDS",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=494,
        branch_to=495,
        rationale="write_html_report is unreached (see section header); has-records raise arc of the dead helper.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 496->497 to 494->495 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-ASSERT-CALL",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=747,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the assert-guard call at its top.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 749 to 747 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-CLASSES",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=748,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the classes projection.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 750 to 748 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-REQUIREMENTS",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=749,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the annotated-requirements projection.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 751 to 749 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-ERRORS",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=752,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the errors projection.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 754 to 752 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-SCOUTS",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=757,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the scouts-summary projection.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 759 to 757 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-DATA",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=767,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the assembled report_data dict.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 769 to 767 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-DEAD-HTML-REPORT-WRITE",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=777,
        branch_to=None,
        rationale="write_html_report is unreached (see section header); the final render+atomic_write_text call.",
        review_reference="Task 24 review: write_outputs no longer calls write_html_report (Task 22, commit ef5dd77). Fix-wave re-pin: line drifted from 779 to 777 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    # --- scout_schedule_cli._assert_blank_identity_scouts_have_no_records IS actively exercised
    # (write_email_reports calls it, and every ART-EMAIL-*/privacy test that constructs a
    # blank-identity scout does so specifically to prove the guard raises), but only the
    # has-records arc: no test constructs a blank-identity scout with genuinely empty
    # classes/requirements (the actual common shape for a scout that failed before identity
    # resolution), so the loop-continues-without-raising arc is never taken.
    BranchExclusion(
        exclusion_id="EXC-SCHEDULE-BLANK-SCOUT-GUARD-NORECORDS-CONTINUES",
        area_id="schedule",
        file="scout_schedule_cli.py",
        line=523,
        branch_to=517,
        rationale=(
            "Every test that builds a blank-identity scout dict for this guard gives it "
            "non-empty classes/requirements specifically to prove the guard raises; none "
            "exercises the passing case (blank identity, empty records) that this arc covers."
        ),
        review_reference="Task 24 review: genuine attempt made; every existing caller targets the raising arc only. Fix-wave re-pin: line drifted from 525->519 to 523->517 after the final-review fix wave's mypy edits to scout_schedule_cli.py (Mapping import, ScoutInput aliasing, and a type: ignore comment on the publish() call all shifted line numbers below them).",
    ),
    # --- pkg-core: core.inference.missing.select_actionable's ancestor walk. `parent_index is
    # None` fires only when a row's own `parent_requirement_number` names a number that never
    # appears as another row's own number within the same (attendee, class) group -- malformed
    # or truncated requirement data. REQ-B-MISSING's two required cases (REQ-EXCLUDE-001/002)
    # exercise the function's actionability filter, not this specific dangling-reference shape.
    BranchExclusion(
        exclusion_id="EXC-PKG-MISSING-DANGLING-PARENT-BREAK",
        area_id="pkg-core",
        file="src/scoutmb/core/inference/missing.py",
        line=69,
        branch_to=None,
        rationale=(
            "Reached only when a row's parent_requirement_number does not match any row's own "
            "number in the same group -- malformed numbering the frozen matrix catalog's two "
            "REQ-EXCLUDE cases do not construct."
        ),
        review_reference="Task 24 review: defensive branch over malformed input, not in the frozen catalog's shapes.",
    ),
    BranchExclusion(
        exclusion_id="EXC-PKG-MISSING-DANGLING-PARENT-BREAK-ARC",
        area_id="pkg-core",
        file="src/scoutmb/core/inference/missing.py",
        line=68,
        branch_to=69,
        rationale="Same dangling-parent-reference case as EXC-PKG-MISSING-DANGLING-PARENT-BREAK.",
        review_reference="Task 24 review: defensive branch over malformed input, not in the frozen catalog's shapes.",
    ),
    # EXC-PKG-PDF-IMPORT-CAPABILITY-EXCEPT / -RAISE removed (Task 24 re-pin review, second
    # pass): adapters.pdf.extract._import_pdf_stack's ImportError-to-CapabilityUnavailable
    # conversion (lines 38-39) was first drafted as subprocess-only-and-thus-invisible, on the
    # premise that this repo's coverage.py setup does not combine subprocess coverage. That
    # premise was wrong -- it does, via pytest-cov's own COV_CORE_* env-var mechanism -- but a
    # separate pytest-cov bug (COV_CORE_BRANCH is derived from pytest-cov's OWN --cov-branch CLI
    # flag, not from `[tool.coverage.run] branch = true`) made every subprocess in the suite
    # write statement-only data, which made `coverage combine` hard-crash rather than silently
    # under-report. Fixed by adding `--cov-branch` to pytest's addopts (see pyproject.toml).
    # With that fixed, tests/packaging/test_core_imports.py's real `python -I` subprocess runs
    # DO show up: verified directly against coverage.json, lines 38-39 are no longer missing.
    # --- pkg-adapters: adapters.pdf.extract.decode_embedded_qr's (pdf-path-level, multi-page)
    # exhaustion fallback. tests/packaging/test_core_imports.py's happy-path test decodes a QR
    # from a one-page PDF, so the loop always returns on its first iteration; no test at this
    # level exercises a PDF whose pages contain no decodable embedded QR at all.
    BranchExclusion(
        exclusion_id="EXC-PKG-PDF-EMBEDDED-EXHAUSTED",
        area_id="pkg-adapters",
        file="src/scoutmb/adapters/pdf/extract.py",
        line=246,
        branch_to=None,
        rationale=(
            "Only the one-page, QR-found happy path is exercised at this entry point "
            "(test_core_imports.py); no caller reaches this level with a PDF that has no "
            "decodable embedded QR on any page."
        ),
        review_reference="Task 24 review: see test_core_imports.py test_decode_embedded_qr_success_path_...",
    ),
    BranchExclusion(
        exclusion_id="EXC-PKG-PDF-EMBEDDED-EXHAUSTED-ARC",
        area_id="pkg-adapters",
        file="src/scoutmb/adapters/pdf/extract.py",
        line=241,
        branch_to=246,
        rationale="Same single-page-always-found gap as EXC-PKG-PDF-EMBEDDED-EXHAUSTED.",
        review_reference="Task 24 review: see test_core_imports.py test_decode_embedded_qr_success_path_...",
    ),
    BranchExclusion(
        exclusion_id="EXC-PKG-PDF-EMBEDDED-CONTINUE-ARC",
        area_id="pkg-adapters",
        file="src/scoutmb/adapters/pdf/extract.py",
        line=243,
        branch_to=241,
        rationale=(
            "The value-not-found-on-this-page loop-continue arc; same single-page-always-found "
            "gap as EXC-PKG-PDF-EMBEDDED-EXHAUSTED (the only test at this entry point supplies a "
            "PDF whose first page already decodes)."
        ),
        review_reference="Task 24 review: see test_core_imports.py test_decode_embedded_qr_success_path_...",
    ),
)
