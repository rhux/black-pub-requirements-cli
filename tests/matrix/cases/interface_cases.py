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
``RUN-ID`` (4), ``RUN-LIST`` (4), and ``UI-ROUTE`` (30 members): the original 23 members whose
observable contract does not require draining an ``asyncio.create_task``-scheduled background
worker to completion (health / status / scouts / pause / resume / runs / open-report /
generate-emails / open-emails-folder), plus the 6 members that DO require actually draining a
background worker (PDF-extract accepted/worker-error, schedule-download accepted/worker-error,
events success/disconnect -- ``UI-ROUTE-024..029``), plus ``UI-ROUTE-030``, the one
``INTENTIONAL_CHANGE`` member characterizing ``open_report``'s unvalidated use of a persisted
``summary.json``'s ``html_report`` field. It also covers ``SSE-FRAME`` (6) and ``SSE-CLEAN`` (4),
a new ``Domain.INTERFACE`` axis pair characterizing the real ``StreamingResponse.body_iterator``
async generator ``ui.server.operation_events`` builds, and the lifecycle cleanup of
``operations``/``busy``/``current_download`` plus the background ``asyncio`` task under success,
worker-exception, terminal-attendee-failure, and client-disconnect. Every case below runs the
REAL ``ui.server`` worker coroutines end to end (through a narrowly-scoped monkeypatch of
``pdf_to_scouts.main``/``scout_schedule_cli.async_main`` -- the exact call boundary
``ui/server.py``'s own workers invoke -- never a reimplementation of their contract), and reads
the REAL SSE frames by iterating the real async generator FastAPI would drive, not by
re-deriving the wire format from source text.
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


@dataclass(frozen=True, slots=True)
class SseFrameObservation:
    """The ordered, fully-parsed sequence of ``data: <json>\\n\\n`` frames a single real
    ``event_stream()`` async generator run yields for one representative scenario -- the
    dicts here are compared against ``json.loads`` of each real observed frame, never against
    the raw wire text (so trailing whitespace/ordering-of-the-generator-not-the-JSON is what is
    pinned, not incidental ``json.dumps`` key ordering, which is stable but not the point under
    test)."""

    frame_types: tuple[str, ...]
    frames: tuple[Mapping[str, object], ...]
    stream_ends: bool = True


@dataclass(frozen=True, slots=True)
class SseCleanObservation:
    """Post-scenario lifecycle-cleanup state, asserted explicitly by the test itself (not left
    to ``load_legacy_ui``'s own exit-time assertions alone) right after each SSE-CLEAN
    scenario."""

    operation_removed: bool
    busy_reset: bool
    current_download_cleared: bool
    task_done: bool


@dataclass(frozen=True, slots=True)
class SseCase:
    meta: CaseMetadata
    expected_by_context: Mapping[str, object]


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
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-024",
            "UI-ROUTE",
            "pdf-accepted",
            ("route",),
            "POST /api/pdf-extract with real files, driven to completion (its "
            "asyncio.create_task(worker()) awaited, pdf_to_scouts.main narrowly monkeypatched "
            "so no real PyMuPDF/opencv decoding runs) writes scouts.csv, pushes a final "
            "'batch_done' event onto the operation's queue followed by the None sentinel, and "
            "resets busy['pdf-extract'] to False.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/pdf-extract",
        expected_by_context={
            "route": InterfaceObservation(status=202, body={"scouts_csv_written": True, "busy_after": False})
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-025",
            "UI-ROUTE",
            "pdf-worker-error",
            ("route",),
            "POST /api/pdf-extract whose worker's call to pdf_to_scouts.main raises: the "
            "worker's own 'except Exception' (ui/server.py:208-209) catches it, pushes an "
            "'error' event with the exception's str(), then the None sentinel, and STILL "
            "resets busy['pdf-extract'] to False in its 'finally' -- the route itself already "
            "returned 202 before the worker ran, so the HTTP response is unaffected by the "
            "later in-worker failure.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/pdf-extract",
        expected_by_context={
            "route": InterfaceObservation(
                status=202, body={"error_message": "boom-pdf", "busy_after": False}
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-026",
            "UI-ROUTE",
            "schedule-accepted",
            ("route",),
            "POST /api/schedule-download, driven to completion (scout_schedule_cli.async_main "
            "narrowly monkeypatched so no real Chromium launches), pushes a final 'batch_done' "
            "event carrying the real summary.json counts and resets both "
            "busy['schedule-download'] and current_download to empty.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download",
        expected_by_context={
            "route": InterfaceObservation(
                status=202,
                body={"scouts_processed": 1, "busy_after": False, "current_download_after": {}},
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-027",
            "UI-ROUTE",
            "schedule-worker-error",
            ("route",),
            "POST /api/schedule-download whose worker's call to scout_schedule_cli.async_main "
            "raises: the worker's own 'except Exception' (ui/server.py:268-269) catches it, "
            "pushes an 'error' event, then the None sentinel, and its 'finally' resets both "
            "busy['schedule-download'] and current_download to empty regardless of the "
            "failure.",
            _EVIDENCE_ROUTES,
        ),
        method="POST",
        route="/api/schedule-download",
        expected_by_context={
            "route": InterfaceObservation(
                status=202,
                body={
                    "error_message": "boom-schedule-mid",
                    "busy_after": False,
                    "current_download_after": {},
                },
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-028",
            "UI-ROUTE",
            "events-success",
            ("route",),
            "GET /api/operations/{operation_id}/events for a real operation that runs to "
            "completion returns 200 text/event-stream and, once the real body_iterator is "
            "fully drained, ends the stream (further iteration raises StopAsyncIteration) -- "
            "the operation_id is also removed from ui.server.operations by the generator's own "
            "'finally' (ui/server.py:310-311).",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/operations/{operation_id}/events",
        expected_by_context={
            "route": InterfaceObservation(
                status=200,
                body={"media_type": "text/event-stream", "operation_removed": True},
            )
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-029",
            "UI-ROUTE",
            "events-disconnect",
            ("route",),
            "Closing the GET /api/operations/{operation_id}/events body_iterator early (before "
            "the None sentinel), simulating a client disconnect, still runs the generator's "
            "'finally' clause (aclose() raises GeneratorExit at the current 'await queue.get()' "
            "suspension point, which the try/finally still observes) -- the operation_id is "
            "removed from ui.server.operations immediately, even though the underlying "
            "background worker task (a separate asyncio.create_task, unrelated to this "
            "generator) is untouched and keeps running to its own completion.",
            _EVIDENCE_ROUTES,
        ),
        method="GET",
        route="/api/operations/{operation_id}/events",
        expected_by_context={
            "route": InterfaceObservation(status=200, body={"operation_removed_after_close": True})
        },
    ),
    InterfaceCase(
        meta=_meta(
            "UI-ROUTE-030",
            "UI-ROUTE",
            "open-report-unvalidated-report-name",
            ("route",),
            "POST /api/runs/{run_id}/open-report reads summary.json's 'html_report' field "
            "(ui/server.py:349) and splices it, completely unvalidated, into the URL passed to "
            "webbrowser.open (ui/server.py:352-353) -- a persisted JSON value containing "
            "path-traversal segments (e.g. '../../elsewhere') flows through unchanged into the "
            "opened URL with no check that it names a plain file inside this run's own "
            "directory. This is intentional-change: Slice 2 owns validating that html_report "
            "resolves to a real file directly under this run_id's own directory before it is "
            "ever used to build a URL.",
            _EVIDENCE_ROUTES,
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation=(
                "open_report rejects (or path-normalizes and re-validates) any html_report "
                "value that is not a bare filename resolving inside RUNS_DIR/<run_id>, instead "
                "of splicing the persisted string directly into an opened URL."
            ),
        ),
        method="POST",
        route="/api/runs/{run_id}/open-report",
        expected_by_context={
            "route": InterfaceObservation(
                status=200, body={"url_contains_unsanitized_value": True}
            )
        },
    ),
)


# ====================================================================================================
# SSE-FRAME-001..006 -- the real ordered sequence of SSE frames ui.server.operation_events'
# body_iterator yields for 6 representative schedule-download scenarios, driven through a
# narrowly-scoped monkeypatch of scout_schedule_cli.async_main (the exact call boundary the real
# worker uses) so every event/frame really passes through the real queue + real event_stream()
# generator, never a hand-built wire-format string. RUN_ID below is a fixed, monkeypatched
# stand-in for the real time-based new_run_id() (see the runner's SSE_FIXED_RUN_ID monkeypatch of new_run_id) -- deterministic
# only because the clock input is controlled, not because any value here was derived by calling
# the function under test.
# ====================================================================================================
SSE_FIXED_RUN_ID = "2026-07-24_TEST"
_EVIDENCE_SSE_FRAME = (
    "ui/server.py:235-273 the schedule-download worker's queue.put calls, and "
    "scout_schedule_cli.py:1810-1853 async_main's own progress_callback calls"
)

SSE_FRAME_CASES: tuple[SseCase, ...] = (
    SseCase(
        meta=_meta(
            "SSE-FRAME-001",
            "SSE-FRAME",
            "zero-scouts-immediate-done",
            ("sse-frame",),
            "With zero scouts loaded, async_main emits exactly one 'batch_start' (total=0) and "
            "the loop body never runs -- the worker then reads the (real, on-disk) summary.json "
            "it wrote and immediately pushes 'batch_done', so the complete real frame sequence "
            "is just those two frames before the None sentinel ends the stream.",
            _EVIDENCE_SSE_FRAME,
        ),
        expected_by_context={
            "sse-frame": SseFrameObservation(
                frame_types=("batch_start", "batch_done"),
                frames=(
                    {"type": "batch_start", "total": 0},
                    {
                        "type": "batch_done",
                        "run_id": SSE_FIXED_RUN_ID,
                        "scouts_processed": 0,
                        "scouts_with_errors": 0,
                        "report_url": None,
                    },
                ),
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-FRAME-002",
            "SSE-FRAME",
            "single-scout-success",
            ("sse-frame",),
            "One scout that completes successfully produces the real 'batch_start' -> "
            "'scout_start' -> 'scout_done' -> 'batch_done' sequence, each frame's fields exactly "
            "as async_main/the worker construct them.",
            _EVIDENCE_SSE_FRAME,
        ),
        expected_by_context={
            "sse-frame": SseFrameObservation(
                frame_types=("batch_start", "scout_start", "scout_done", "batch_done"),
                frames=(
                    {"type": "batch_start", "total": 1},
                    {"type": "scout_start", "index": 1, "total": 1, "name": "Avery Archer"},
                    {
                        "type": "scout_done",
                        "index": 1,
                        "total": 1,
                        "name": "Avery Archer",
                        "attendee_id": "90000001",
                        "classes": 2,
                        "requirements": 3,
                        "errors": 0,
                    },
                    {
                        "type": "batch_done",
                        "run_id": SSE_FIXED_RUN_ID,
                        "scouts_processed": 1,
                        "scouts_with_errors": 0,
                        "report_url": None,
                    },
                ),
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-FRAME-003",
            "SSE-FRAME",
            "pause-then-resume",
            ("sse-frame",),
            "A download paused before its one scout starts, then resumed: async_main's own "
            "resume_event check (scout_schedule_cli.py:1821-1826) emits 'paused' then, once the "
            "event is set again, 'resumed', BEFORE 'scout_start' -- both carrying the same "
            "index/total the pending scout would have.",
            _EVIDENCE_SSE_FRAME,
        ),
        expected_by_context={
            "sse-frame": SseFrameObservation(
                frame_types=("batch_start", "paused", "resumed", "scout_start", "scout_done", "batch_done"),
                frames=(
                    {"type": "batch_start", "total": 1},
                    {"type": "paused", "index": 1, "total": 1},
                    {"type": "resumed", "index": 1, "total": 1},
                    {"type": "scout_start", "index": 1, "total": 1, "name": "Avery Archer"},
                    {
                        "type": "scout_done",
                        "index": 1,
                        "total": 1,
                        "name": "Avery Archer",
                        "attendee_id": "90000001",
                        "classes": 2,
                        "requirements": 3,
                        "errors": 0,
                    },
                    {
                        "type": "batch_done",
                        "run_id": SSE_FIXED_RUN_ID,
                        "scouts_processed": 1,
                        "scouts_with_errors": 0,
                        "report_url": None,
                    },
                ),
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-FRAME-004",
            "SSE-FRAME",
            "two-scouts-no-pause",
            ("sse-frame",),
            "Two scouts, both succeeding, with no pause: the 'scout_start'/'scout_done' pair "
            "repeats once per scout, in order, between the single 'batch_start' and 'batch_done'.",
            _EVIDENCE_SSE_FRAME,
        ),
        expected_by_context={
            "sse-frame": SseFrameObservation(
                frame_types=(
                    "batch_start",
                    "scout_start",
                    "scout_done",
                    "scout_start",
                    "scout_done",
                    "batch_done",
                ),
                frames=(
                    {"type": "batch_start", "total": 2},
                    {"type": "scout_start", "index": 1, "total": 2, "name": "Avery Archer"},
                    {
                        "type": "scout_done",
                        "index": 1,
                        "total": 2,
                        "name": "Avery Archer",
                        "attendee_id": "90000001",
                        "classes": 2,
                        "requirements": 3,
                        "errors": 0,
                    },
                    {"type": "scout_start", "index": 2, "total": 2, "name": "Bo Baker"},
                    {
                        "type": "scout_done",
                        "index": 2,
                        "total": 2,
                        "name": "Bo Baker",
                        "attendee_id": "90000002",
                        "classes": 1,
                        "requirements": 1,
                        "errors": 0,
                    },
                    {
                        "type": "batch_done",
                        "run_id": SSE_FIXED_RUN_ID,
                        "scouts_processed": 2,
                        "scouts_with_errors": 0,
                        "report_url": None,
                    },
                ),
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-FRAME-005",
            "SSE-FRAME",
            "worker-exception-mid-batch",
            ("sse-frame",),
            "async_main raising partway through (after 'scout_start' but before that scout's "
            "'scout_done') is caught by the worker's own 'except Exception' (ui/server.py:"
            "268-269): the real frame sequence is 'batch_start', 'scout_start', then 'error' "
            "-- no 'scout_done' and no 'batch_done' -- and the stream still ends cleanly right "
            "after (the None sentinel is always pushed in the worker's 'finally').",
            _EVIDENCE_SSE_FRAME,
        ),
        expected_by_context={
            "sse-frame": SseFrameObservation(
                frame_types=("batch_start", "scout_start", "error"),
                frames=(
                    {"type": "batch_start", "total": 1},
                    {"type": "scout_start", "index": 1, "total": 1, "name": "Avery Archer"},
                    {"type": "error", "message": "boom-schedule-mid"},
                ),
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-FRAME-006",
            "SSE-FRAME",
            "two-scouts-one-non-fatal-error",
            ("sse-frame",),
            "Two scouts where the second's own result carries a non-fatal per-scout error "
            "(process_scout recorded it, the batch itself still completes): 'scout_done''s own "
            "'errors' field is 1 for that scout, and the batch still reaches a real "
            "'batch_done' whose 'scouts_with_errors' reflects it -- there is no 'error'-typed "
            "frame at all for this kind of failure, only the ordinary per-scout fields.",
            _EVIDENCE_SSE_FRAME,
        ),
        expected_by_context={
            "sse-frame": SseFrameObservation(
                frame_types=(
                    "batch_start",
                    "scout_start",
                    "scout_done",
                    "scout_start",
                    "scout_done",
                    "batch_done",
                ),
                frames=(
                    {"type": "batch_start", "total": 2},
                    {"type": "scout_start", "index": 1, "total": 2, "name": "Avery Archer"},
                    {
                        "type": "scout_done",
                        "index": 1,
                        "total": 2,
                        "name": "Avery Archer",
                        "attendee_id": "90000001",
                        "classes": 2,
                        "requirements": 3,
                        "errors": 0,
                    },
                    {"type": "scout_start", "index": 2, "total": 2, "name": "Bo Baker"},
                    {
                        "type": "scout_done",
                        "index": 2,
                        "total": 2,
                        "name": "Bo Baker",
                        "attendee_id": "90000002",
                        "classes": 0,
                        "requirements": 0,
                        "errors": 1,
                    },
                    {
                        "type": "batch_done",
                        "run_id": SSE_FIXED_RUN_ID,
                        "scouts_processed": 2,
                        "scouts_with_errors": 1,
                        "report_url": None,
                    },
                ),
            )
        },
    ),
)


# ====================================================================================================
# SSE-CLEAN-001..004 -- lifecycle cleanup of operations/busy/current_download plus the background
# asyncio task, for success, worker-exception, terminal-attendee-failure, and client-disconnect.
# Each scenario reuses the SAME real worker/queue/generator machinery as SSE-FRAME above.
# ====================================================================================================
_EVIDENCE_SSE_CLEAN = (
    "ui/server.py:238-273 the schedule-download worker's try/except/finally, and "
    "ui/server.py:303-311 operation_events' event_stream() try/finally"
)

SSE_CLEAN_CASES: tuple[SseCase, ...] = (
    SseCase(
        meta=_meta(
            "SSE-CLEAN-001",
            "SSE-CLEAN",
            "success",
            ("sse-clean",),
            "After a schedule-download operation's real body_iterator is fully drained to its "
            "'batch_done' + None sentinel, the operation_id is gone from ui.server.operations, "
            "busy['schedule-download'] is back to False, current_download is back to {}, and "
            "the background asyncio task the POST route created has actually finished (not "
            "merely cancelled).",
            _EVIDENCE_SSE_CLEAN,
        ),
        expected_by_context={
            "sse-clean": SseCleanObservation(
                operation_removed=True,
                busy_reset=True,
                current_download_cleared=True,
                task_done=True,
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-CLEAN-002",
            "SSE-CLEAN",
            "worker-exception",
            ("sse-clean",),
            "After a schedule-download whose async_main raises mid-batch is fully drained (its "
            "'error' frame followed by the None sentinel), the worker's 'finally' clause still "
            "runs -- the operation, busy flag, and current_download are cleaned up identically "
            "to the success case, and the background task still finished (it caught its own "
            "exception internally; it was never left pending).",
            _EVIDENCE_SSE_CLEAN,
        ),
        expected_by_context={
            "sse-clean": SseCleanObservation(
                operation_removed=True,
                busy_reset=True,
                current_download_cleared=True,
                task_done=True,
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-CLEAN-003",
            "SSE-CLEAN",
            "terminal-attendee-failure",
            ("sse-clean",),
            "After a schedule-download where one scout's own result carries a non-fatal error "
            "(the batch itself still reaches 'batch_done') is fully drained, cleanup is "
            "identical to the success case -- a per-scout failure that does not raise out of "
            "async_main is not distinguished from a fully clean run by any of "
            "operations/busy/current_download/task state.",
            _EVIDENCE_SSE_CLEAN,
        ),
        expected_by_context={
            "sse-clean": SseCleanObservation(
                operation_removed=True,
                busy_reset=True,
                current_download_cleared=True,
                task_done=True,
            )
        },
    ),
    SseCase(
        meta=_meta(
            "SSE-CLEAN-004",
            "SSE-CLEAN",
            "client-disconnect",
            ("sse-clean",),
            "Closing the body_iterator early (aclose(), simulating a client disconnect) after "
            "only one frame is consumed removes the operation_id from ui.server.operations "
            "IMMEDIATELY (the generator's own 'finally' runs on GeneratorExit) -- but the "
            "background worker task is a SEPARATE asyncio.create_task the disconnect does "
            "nothing to: it keeps running unattended and only busy/current_download reset, and "
            "the task itself finish, once IT independently completes afterward. Both facts are "
            "asserted here: the operation is gone right away, and busy/current_download/task "
            "state also end up clean once the detached worker finishes on its own.",
            _EVIDENCE_SSE_CLEAN,
        ),
        expected_by_context={
            "sse-clean": SseCleanObservation(
                operation_removed=True,
                busy_reset=True,
                current_download_cleared=True,
                task_done=True,
            )
        },
    ),
)


INTERFACE_CASES: tuple[InterfaceCase, ...] = (
    INTERFACE_CASES_IMPORT
    + INTERFACE_CASES_METHOD
    + INTERFACE_CASES_RUN_ID
    + INTERFACE_CASES_RUN_LIST
    + INTERFACE_CASES_ROUTE
)

ALL_INTERFACE_METADATA: tuple[CaseMetadata, ...] = (
    tuple(case.meta for case in INTERFACE_CASES)
    + tuple(case.meta for case in SSE_FRAME_CASES)
    + tuple(case.meta for case in SSE_CLEAN_CASES)
)
