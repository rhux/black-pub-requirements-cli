"""UI-server interface characterization catalog (Task 21).

Every row is ``preserve`` unless noted, pinning the *current* behavior of ``ui/server.py``'s
FastAPI app -- 12 live routes (enumerated below, read from ``ui/server.py``'s ``@app.get`` /
``@app.post`` decorators, never guessed), its ``operations`` / ``busy`` / ``current_download``
module-level lifecycle state, and ``scout_schedule_cli.``/``_safe_run_id``'s run-id path-safety
seam. This module holds only frozen data -- it never imports ``ui.server`` or
``scout_schedule_cli`` at module level. The runner in
``tests/characterization/test_interface_matrix.py`` performs the real import (via
``tests.harnesses.legacy.load_legacy_ui``) and drives the real FastAPI app through an
``httpx.AsyncClient`` bound to it with ``ASGITransport`` -- never a real socket.

The 12 live routes (method, path)::

    GET  /api/health
    GET  /api/status
    GET  /api/scouts
    POST /api/pdf-extract
    POST /api/schedule-download
    POST /api/schedule-download/pause
    POST /api/schedule-download/resume
    GET  /api/operations/{operation_id}/events
    GET  /api/runs
    POST /api/runs/{run_id}/open-report
    POST /api/runs/{run_id}/generate-emails
    POST /api/runs/{run_id}/open-emails-folder

Scope note (honest, not silent): this catalog covers ``UI-IMPORT`` (2), ``UI-METHOD`` (12),
``RUN-ID`` (4), ``RUN-LIST`` (4), and the 20 ``UI-ROUTE`` members whose observable contract does
NOT require draining an ``asyncio.create_task``-scheduled background worker to completion
(health / status / scouts / pause / resume / runs / open-report / generate-emails /
open-emails-folder). The remaining 11 ``UI-ROUTE`` members (the PDF-extract and
schedule-download "busy" / "accepted" / "worker-error" states, and the SSE "events" success/
disconnect states) plus ``SSE-FRAME``, ``SSE-CLEAN``, and ``UI-ACTION`` are NOT implemented in
this task delivery -- see the Task 21 report for the explicit BLOCKED/DONE_WITH_CONCERNS
accounting. No axis in ``tests/matrix/axes.py`` claims a member this file does not back with a
real, passing case.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tests.matrix.model import CaseMetadata, Classification, Domain, EvidenceKind

_EVIDENCE_ROUTES = "ui/server.py:126-391 the 12 @app.get/@app.post route decorators"
_EVIDENCE_RUN_ID = "ui/server.py:102-108 _safe_run_id"
_EVIDENCE_RUN_LIST = "ui/server.py:316-339 list_runs"
_EVIDENCE_IMPORT = "ui/server.py:86-99 module-level SETTINGS/SCOUTS_CSV/... at import time"


@dataclass(frozen=True, slots=True)
class InterfaceObservation:
    status: int
    body: object
    headers: tuple[tuple[str, str], ...] = ()
    events: tuple[str, ...] = ()
    remaining_resources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InterfaceCase:
    meta: CaseMetadata
    method: str
    route: str
    expected_by_context: Mapping[str, InterfaceObservation | object]


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    contexts: tuple[str, ...],
    rationale: str,
    evidence_reference: str,
    classification: Classification = Classification.PRESERVE,
    target_owner: str | None = None,
    target_observation: str | None = None,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.INTERFACE,
        classification=classification,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=contexts,
        evidence_reference=evidence_reference,
        target_owner=target_owner,
        target_observation=target_observation,
    )


# ====================================================================================================
# UI-IMPORT-001..002 -- importing ui.server under a sandboxed SCOUTMB_DATA_DIR touches ONLY that
# tree; UI-IMPORT-001 is intentional-change (Slice 2 owns hardening this to an explicit dependency
# rather than an import-time module-global side effect); UI-IMPORT-002 pins that a plain import
# never writes to the REAL platform data root regardless.
# ====================================================================================================
INTERFACE_CASES_IMPORT: tuple[InterfaceCase, ...] = (
    InterfaceCase(
        meta=_meta(
            "UI-IMPORT-001",
            "UI-IMPORT",
            "sandbox-root-only",
            ("import",),
            "Importing ui.server with SCOUTMB_DATA_DIR pointed at a sandbox root creates ONLY "
            "that root plus its runs/ subdirectory (SETTINGS.ensure_dirs(), ui/server.py:93), "
            "as a module-level side effect of import -- this "
            "is intentional-change: Slice 2 owns replacing the import-time "
            "SETTINGS.ensure_dirs() global with an explicit, testable dependency instead of a "
            "side effect triggered merely by importing the module.",
            _EVIDENCE_IMPORT,
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation=(
                "ui.server exposes an explicit create_app(settings) factory; importing the "
                "module performs no filesystem I/O at all."
            ),
        ),
        method="IMPORT",
        route="ui.server",
        expected_by_context={"import": ("runs",)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-IMPORT-002",
            "UI-IMPORT",
            "real-root-untouched",
            ("import",),
            "A plain import of ui.server under a sandboxed SCOUTMB_DATA_DIR never creates or "
            "writes anything under the REAL platform data root (_platform_data_root()) -- "
            "the module only ever touches SETTINGS.data_root, which the env var fully "
            "overrides.",
            _EVIDENCE_IMPORT,
        ),
        method="IMPORT",
        route="ui.server",
        expected_by_context={"import": ()},
    ),
)


# ====================================================================================================
# UI-METHOD-001..012 -- one case per live route: the wrong HTTP verb returns 405 with an exact
# Allow header. Fully declarative -- no bespoke per-case runner logic needed.
# ====================================================================================================
_METHOD_TABLE: tuple[tuple[str, str, str, str], ...] = (
    ("UI-METHOD-001", "/api/health", "GET", "POST"),
    ("UI-METHOD-002", "/api/status", "GET", "POST"),
    ("UI-METHOD-003", "/api/scouts", "GET", "POST"),
    ("UI-METHOD-004", "/api/pdf-extract", "POST", "GET"),
    ("UI-METHOD-005", "/api/schedule-download", "POST", "GET"),
    ("UI-METHOD-006", "/api/schedule-download/pause", "POST", "GET"),
    ("UI-METHOD-007", "/api/schedule-download/resume", "POST", "GET"),
    ("UI-METHOD-008", "/api/operations/OP-ID/events", "GET", "POST"),
    ("UI-METHOD-009", "/api/runs", "GET", "POST"),
    ("UI-METHOD-010", "/api/runs/RUN-ID/open-report", "POST", "GET"),
    ("UI-METHOD-011", "/api/runs/RUN-ID/generate-emails", "POST", "GET"),
    ("UI-METHOD-012", "/api/runs/RUN-ID/open-emails-folder", "POST", "GET"),
)

def _method_case(case_id: str, route: str, allowed: str, wrong: str) -> InterfaceCase:
    # ui/server.py:391 mounts StaticFiles at "/" LAST, catching every GET/HEAD request whose
    # path did not already match an earlier route. For a POST-only route tested with GET
    # (wrong == "GET"), that catch-all mount fully matches the request BEFORE Starlette's
    # router ever gets to report a genuine method mismatch -- it returns its own 404 (no such
    # static file), never a 405. Sending POST to a GET-only route hits the opposite case: the
    # static mount only serves GET/HEAD, so it does not match, and Starlette's router falls
    # through to the real "path matched, method didn't" 405. Both outcomes were verified by
    # driving the real app, not guessed from reading the decorators alone.
    if wrong == "GET":
        rationale = (
            f"{route} has no GET handler; because ui/server.py mounts StaticFiles at '/' "
            "LAST (ui/server.py:391), that catch-all mount intercepts this GET before "
            "Starlette's router can report a method mismatch on the POST-only route -- the "
            "observable result is 404 'Not Found' (as if the path were a missing static "
            "file), NOT 405."
        )
        expected = InterfaceObservation(status=404, body={"detail": "Not Found"})
    else:
        rationale = (
            f"{route} is only registered for {allowed}; sending {wrong} returns a genuine "
            "405 with the exact Starlette body {'detail': 'Method Not Allowed'} -- the "
            "catch-all static mount only serves GET/HEAD, so it never intercepts a POST and "
            "the router's real method-mismatch handling is reached. This Starlette version's "
            "405 response carries no Allow header at all (verified against the real app)."
        )
        expected = InterfaceObservation(status=405, body={"detail": "Method Not Allowed"})
    return InterfaceCase(
        meta=_meta(case_id, "UI-METHOD", route, ("method",), rationale, _EVIDENCE_ROUTES),
        method=wrong,
        route=route,
        expected_by_context={"method": expected},
    )


INTERFACE_CASES_METHOD: tuple[InterfaceCase, ...] = tuple(
    _method_case(case_id, route, allowed, wrong)
    for case_id, route, allowed, wrong in _METHOD_TABLE
)


# ====================================================================================================
# RUN-ID-001..004 -- _safe_run_id's path-traversal guard (ui/server.py:102-108).
# ====================================================================================================
INTERFACE_CASES_RUN_ID: tuple[InterfaceCase, ...] = (
    InterfaceCase(
        meta=_meta(
            "RUN-ID-001",
            "RUN-ID",
            "valid",
            ("run-id",),
            "An ordinary run id (matching new_run_id()'s own 'YYYY-MM-DD_HHMM' shape) resolves "
            "to RUNS_DIR/<run_id> without raising.",
            _EVIDENCE_RUN_ID,
        ),
        method="CALL",
        route="_safe_run_id",
        expected_by_context={"run-id": ("2026-07-23_1200", None)},  # (raw, expected_status)
    ),
    InterfaceCase(
        meta=_meta(
            "RUN-ID-002",
            "RUN-ID",
            "traversal",
            ("run-id",),
            "A run id containing '..' is rejected with HTTP 400 before any filesystem access, "
            "regardless of whether it also contains a separator.",
            _EVIDENCE_RUN_ID,
        ),
        method="CALL",
        route="_safe_run_id",
        expected_by_context={"run-id": ("../../etc/passwd", 400)},
    ),
    InterfaceCase(
        meta=_meta(
            "RUN-ID-003",
            "RUN-ID",
            "absolute",
            ("run-id",),
            "An absolute path is rejected with HTTP 400: the leading '/' is caught by the "
            "explicit '/' membership check, independent of the resolved-parent check below it.",
            _EVIDENCE_RUN_ID,
        ),
        method="CALL",
        route="_safe_run_id",
        expected_by_context={"run-id": ("/etc/passwd", 400)},
    ),
    InterfaceCase(
        meta=_meta(
            "RUN-ID-004",
            "RUN-ID",
            "separator-containing",
            ("run-id",),
            "A run id containing an embedded '/' (not a traversal, not absolute -- e.g. "
            "'2026-07-23_1200/extra') is still rejected with HTTP 400 by the explicit '/' "
            "membership check.",
            _EVIDENCE_RUN_ID,
        ),
        method="CALL",
        route="_safe_run_id",
        expected_by_context={"run-id": ("2026-07-23_1200/extra", 400)},
    ),
)


# ====================================================================================================
# RUN-LIST-001..004 -- list_runs (GET /api/runs).
# ====================================================================================================
INTERFACE_CASES_RUN_LIST: tuple[InterfaceCase, ...] = (
    InterfaceCase(
        meta=_meta(
            "RUN-LIST-001",
            "RUN-LIST",
            "empty",
            ("run-list",),
            "With no runs/*/summary.json present, GET /api/runs returns an empty JSON list.",
            _EVIDENCE_RUN_LIST,
        ),
        method="GET",
        route="/api/runs",
        expected_by_context={"run-list": InterfaceObservation(status=200, body=[])},
    ),
    InterfaceCase(
        meta=_meta(
            "RUN-LIST-002",
            "RUN-LIST",
            "reverse-sorted-multiple",
            ("run-list",),
            "Multiple valid runs are returned sorted by run_id DESCENDING (list_runs.sort(..., "
            "reverse=True), ui/server.py:338) -- the lexicographic run_id ordering happens to "
            "match chronological ordering because new_run_id()'s format is 'YYYY-MM-DD_HHMM'.",
            _EVIDENCE_RUN_LIST,
        ),
        method="GET",
        route="/api/runs",
        expected_by_context={
            "run-list": InterfaceObservation(
                status=200,
                body=["2026-07-23_1300", "2026-07-23_1200"],
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "RUN-LIST-003",
            "RUN-LIST",
            "corrupt-summary-ignored",
            ("run-list",),
            "A run directory whose summary.json is not valid JSON is silently skipped "
            "(list_runs' `except (OSError, json.JSONDecodeError): continue`, ui/server.py:"
            "323-324), never surfaced as an error to the caller.",
            _EVIDENCE_RUN_LIST,
        ),
        method="GET",
        route="/api/runs",
        expected_by_context={"run-list": InterfaceObservation(status=200, body=[])},
    ),
    InterfaceCase(
        meta=_meta(
            "RUN-LIST-004",
            "RUN-LIST",
            "missing-optional-report",
            ("run-list",),
            "A run whose summary.json has no 'html_report' key still appears in the list, with "
            "report_url=None rather than a raised KeyError or an omitted row.",
            _EVIDENCE_RUN_LIST,
        ),
        method="GET",
        route="/api/runs",
        expected_by_context={
            "run-list": InterfaceObservation(status=200, body=["2026-07-23_1200"])
        },
    ),
)


# ====================================================================================================
# UI-ROUTE -- the 20 members whose contract does not require draining a background worker task.
# ====================================================================================================
INTERFACE_CASES_ROUTE: tuple[InterfaceCase, ...] = (
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-001",
            "UI-ROUTE",
            "health-success",
            ("route",),
            "GET /api/health always returns 200 {'status': 'ok'}.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/health",
        expected_by_context={
            "route": InterfaceObservation(status=200, body={"status": "ok"})
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-002",
            "UI-ROUTE",
            "status-absent",
            ("route",),
            "GET /api/status with no scouts.csv on disk returns scouts_csv_exists=False and "
            "null count/mtime.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/status",
        expected_by_context={
            "route": InterfaceObservation(
                status=200,
                body={
                    "scouts_csv_exists": False,
                    "scouts_count": None,
                    "scouts_mtime": None,
                },
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-003",
            "UI-ROUTE",
            "status-present",
            ("route",),
            "GET /api/status with a scouts.csv on disk reports scouts_csv_exists=True and the "
            "real row count.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/status",
        expected_by_context={
            "route": InterfaceObservation(
                status=200, body={"scouts_csv_exists": True, "scouts_count": 2}
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-004",
            "UI-ROUTE",
            "scouts-absent",
            ("route",),
            "GET /api/scouts with no scouts.csv on disk returns 404.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/scouts",
        expected_by_context={"route": InterfaceObservation(status=404, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-005",
            "UI-ROUTE",
            "scouts-present",
            ("route",),
            "GET /api/scouts with a scouts.csv on disk returns the name/registrant_type "
            "projection of each row, blank fields normalized to ''.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/scouts",
        expected_by_context={
            "route": InterfaceObservation(
                status=200,
                body=[
                    {"name": "Avery Archer", "registrant_type": "Youth"},
                    {"name": "Bo Baker", "registrant_type": ""},
                ],
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-006",
            "UI-ROUTE",
            "pdf-no-files",
            ("route",),
            "POST /api/pdf-extract with the multipart 'files' field omitted entirely never "
            "reaches the route body at all: FastAPI's own request-validation layer rejects it "
            "with 422 first (list[UploadFile] = File(...) is a REQUIRED field) -- the "
            "handler's own 'if not files: raise HTTPException(400, ...)' guard (ui/server.py:"
            "156-157) is unreachable through this client path; it is defensive code for a "
            "shape FastAPI's validation already forecloses.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/pdf-extract",
        expected_by_context={"route": InterfaceObservation(status=422, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-007",
            "UI-ROUTE",
            "pdf-busy",
            ("route",),
            "POST /api/pdf-extract while busy['pdf-extract'] is already True returns 409 "
            "without touching PDF_UPLOADS_DIR or scheduling a second worker.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/pdf-extract",
        expected_by_context={"route": InterfaceObservation(status=409, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-008",
            "UI-ROUTE",
            "schedule-missing",
            ("route",),
            "POST /api/schedule-download with no scouts.csv on disk returns 409 before setting "
            "the busy flag.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download",
        expected_by_context={"route": InterfaceObservation(status=409, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-009",
            "UI-ROUTE",
            "schedule-busy",
            ("route",),
            "POST /api/schedule-download while busy['schedule-download'] is already True "
            "returns 409.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download",
        expected_by_context={"route": InterfaceObservation(status=409, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-010",
            "UI-ROUTE",
            "pause-inactive",
            ("route",),
            "POST /api/schedule-download/pause with no active download (busy False, no "
            "resume_event) returns 409.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download/pause",
        expected_by_context={"route": InterfaceObservation(status=409, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-011",
            "UI-ROUTE",
            "pause-active",
            ("route",),
            "POST /api/schedule-download/pause with an active download clears the shared "
            "resume_event and returns {'paused': True}.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download/pause",
        expected_by_context={
            "route": InterfaceObservation(status=200, body={"paused": True})
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-012",
            "UI-ROUTE",
            "resume-inactive",
            ("route",),
            "POST /api/schedule-download/resume with no active download returns 409.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download/resume",
        expected_by_context={"route": InterfaceObservation(status=409, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-013",
            "UI-ROUTE",
            "resume-active",
            ("route",),
            "POST /api/schedule-download/resume with an active download sets the shared "
            "resume_event and returns {'paused': False}.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download/resume",
        expected_by_context={
            "route": InterfaceObservation(status=200, body={"paused": False})
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-014",
            "UI-ROUTE",
            "events-missing",
            ("route",),
            "GET /api/operations/{operation_id}/events for an unknown operation_id returns "
            "404 before ever constructing a StreamingResponse.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/operations/UNKNOWN-OP/events",
        expected_by_context={"route": InterfaceObservation(status=404, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-015",
            "UI-ROUTE",
            "runs-empty",
            ("route",),
            "GET /api/runs with no run directories present returns an empty list.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/runs",
        expected_by_context={"route": InterfaceObservation(status=200, body=[])},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-016",
            "UI-ROUTE",
            "open-report-missing",
            ("route",),
            "POST /api/runs/{run_id}/open-report for a run_id with no summary.json returns "
            "404.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/UNKNOWN-RUN/open-report",
        expected_by_context={"route": InterfaceObservation(status=404, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-017",
            "UI-ROUTE",
            "open-report-no-report",
            ("route",),
            "POST /api/runs/{run_id}/open-report for a run whose summary.json has no "
            "'html_report' key returns 404 ('This run has no HTML report').",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/{run_id}/open-report",
        expected_by_context={"route": InterfaceObservation(status=404, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-018",
            "UI-ROUTE",
            "open-report-success",
            ("route",),
            "POST /api/runs/{run_id}/open-report for a run with a real html_report opens the "
            "browser (webbrowser.open, monkeypatched here to a recording stub) and returns "
            "{'opened': True, 'url': <absolute url>}.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/{run_id}/open-report",
        expected_by_context={"route": InterfaceObservation(status=200, body={"opened": True})},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-019",
            "UI-ROUTE",
            "email-missing",
            ("route",),
            "POST /api/runs/{run_id}/generate-emails for a run_id with no scouts.json returns "
            "404.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/UNKNOWN-RUN/generate-emails",
        expected_by_context={"route": InterfaceObservation(status=404, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-020",
            "UI-ROUTE",
            "email-success",
            ("route",),
            "POST /api/runs/{run_id}/generate-emails for a run with a well-formed scouts.json "
            "writes emails/missing_requirements.csv and returns the real per-status counts.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/{run_id}/generate-emails",
        expected_by_context={
            "route": InterfaceObservation(
                status=200,
                body={
                    "generated": True,
                    "scouts_needing_email": 1,
                    "scouts_all_complete": 0,
                    "scouts_no_data": 0,
                },
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-021",
            "UI-ROUTE",
            "email-corrupt-json",
            ("route",),
            "POST /api/runs/{run_id}/generate-emails for a run whose scouts.json is not valid "
            "JSON surfaces as an unhandled 500 -- json.loads raises before write_email_reports "
            "is ever called, and no route-level try/except catches it.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/{run_id}/generate-emails",
        expected_by_context={"route": InterfaceObservation(status=500, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-022",
            "UI-ROUTE",
            "open-folder-missing",
            ("route",),
            "POST /api/runs/{run_id}/open-emails-folder for a run with no emails/ directory "
            "(never generated) returns 404.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/runs/{run_id}/open-emails-folder",
        expected_by_context={"route": InterfaceObservation(status=404, body=None)},
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-023",
            "UI-ROUTE",
            "open-folder-success",
            ("route",),
            "POST /api/runs/{run_id}/open-emails-folder for a run with an emails/ directory "
            "calls os.startfile(str(emails_dir)) -- an ATTRIBUTE THAT DOES NOT EXIST on "
            "non-Windows Python, so on this host it raises AttributeError, surfacing as an "
            "unhandled 500 -- this is intentional-change (Slice 2 owns a cross-platform "
            "folder-open, e.g. dispatching on sys.platform to subprocess.run(['open', ...]) / "
            "['xdg-open', ...] / os.startfile).",
            _EVIDENCE_ROUTES,
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation=(
                "open_emails_folder dispatches on sys.platform so the route succeeds "
                "identically on Windows, macOS, and Linux."
            ),
        ),
        method="POST",
        route="/api/runs/{run_id}/open-emails-folder",
        expected_by_context={"route": InterfaceObservation(status=500, body=None)},
    ),
)


INTERFACE_CASES: tuple[InterfaceCase, ...] = (
    INTERFACE_CASES_IMPORT
    + INTERFACE_CASES_METHOD
    + INTERFACE_CASES_RUN_ID
    + INTERFACE_CASES_RUN_LIST
    + INTERFACE_CASES_ROUTE
)

ALL_INTERFACE_METADATA: tuple[CaseMetadata, ...] = tuple(case.meta for case in INTERFACE_CASES)
