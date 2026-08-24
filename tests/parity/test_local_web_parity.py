"""D13 parity: the package's create_app(settings) routes must match ui/server.py's (now-fixed)
routes on status code and response body shape, for the same request. Both apps are driven
in-process via httpx.ASGITransport -- the same mechanism tests/characterization/
test_interface_matrix.py already uses for the legacy app -- never a real socket.

_client_for wraps app.router.lifespan_context(app), not just ASGITransport -- ASGITransport
alone does NOT run FastAPI's lifespan, so app.state.settings/job_registry (set inside create_app's
lifespan, Task B8.1) would never be populated and every route touching request.app.state would
raise AttributeError before any assertion ran. An earlier draft of this test file had exactly
that bug."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.matrix.cases.interface_cases import (
    INTERFACE_CASES_METHOD,
    INTERFACE_CASES_RUN_ID,
    SSE_CLEAN_CASES,
    SSE_FIXED_RUN_ID,
    SSE_FRAME_CASES,
    SseCleanObservation,
)
from tests.matrix.pytest_support import execution_params

from scoutmb.config import UiSettings
from scoutmb.interfaces.web import routes as routes_module
from scoutmb.interfaces.web.app import create_app

_SCOUTS_CSV_BODY = (
    "Attendee Name,Registrant Type,QR Code Contents\r\n"
    "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n"
)


@asynccontextmanager
async def _client_for(data_root: Path) -> AsyncIterator[tuple[httpx.AsyncClient, UiSettings]]:
    settings = UiSettings(data_root=data_root)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, settings


def _tasks_snapshot() -> set:
    return set(asyncio.all_tasks())


def _only_spawned_task(before: set) -> asyncio.Task:
    spawned = set(asyncio.all_tasks()) - before
    assert len(spawned) == 1, f"expected exactly one spawned worker task, got {spawned}"
    return next(iter(spawned))


async def _drain(client: httpx.AsyncClient, operation_id: str) -> list[dict[str, Any]]:
    async with client.stream("GET", f"/api/operations/{operation_id}/events") as resp:
        events: list[dict[str, Any]] = []
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                payload = frame.removeprefix("data: ")
                events.append(json.loads(payload))
        return events


def _fake_pdf_main_success(csv_body: str):
    def fake(argv: list[str], *, progress_callback=None) -> int:
        if progress_callback is not None:
            progress_callback(1, 1, Path(argv[0]))
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text(csv_body, encoding="utf-8-sig")
        return 0

    return fake


def _fake_pdf_main_error(message: str):
    def fake(argv: list[str], *, progress_callback=None) -> int:
        raise RuntimeError(message)

    return fake


def _fake_schedule_async_main(*, summary_extra: dict | None = None, raise_message: str | None = None):
    async def fake(config, *, progress_callback=None, resume_event=None) -> int:
        if raise_message is not None:
            raise RuntimeError(raise_message)
        config.output.mkdir(parents=True, exist_ok=True)
        summary = {
            "scouts_processed": 1,
            "scouts_with_errors": 0,
            "generated_at_local": "2026-07-24 00:00",
            "generated_at_iso": "2026-07-24T00:00:00",
            "classes": 0,
            "requirements": 0,
            "html_report": None,
        }
        summary.update(summary_extra or {})
        (config.output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return 0

    return fake


@pytest.mark.matrix_case(case_id="UI-ROUTE-001", context_id="route", lane="default")
async def test_health_route_matches(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.matrix_case(case_id="UI-ROUTE-004", context_id="route", lane="default")
async def test_scouts_csv_missing_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/api/scouts")
    assert response.status_code == 404


@pytest.mark.matrix_case(case_id="UI-ROUTE-002", context_id="route", lane="default")
async def test_status_route_reports_no_csv(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "scouts_csv_exists": False,
        "scouts_count": None,
        "scouts_mtime": None,
    }


@pytest.mark.matrix_case(case_id="UI-ROUTE-003", context_id="route", lane="default")
async def test_status_route_reports_real_csv(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        status_resp = await client.get("/api/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["scouts_csv_exists"] is True
    assert status_resp.json()["scouts_count"] == 1


@pytest.mark.matrix_case(case_id="UI-ROUTE-005", context_id="route", lane="default")
async def test_scouts_route_reports_real_csv(tmp_path: Path) -> None:
    """UI-ROUTE-005: the second row's blank Registrant Type must normalize to '', not None or
    a missing key -- mirrors the catalog's exact two-row scenario."""
    two_row_csv = (
        "Attendee Name,Registrant Type,QR Code Contents\r\n"
        "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n"
        "Bo Baker,,https://scoutingevent.com/mobile/y\r\n"
    )
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(two_row_csv, encoding="utf-8-sig")
        scouts_resp = await client.get("/api/scouts")
    assert scouts_resp.status_code == 200
    assert scouts_resp.json() == [
        {"name": "Avery Archer", "registrant_type": "Youth"},
        {"name": "Bo Baker", "registrant_type": ""},
    ]


@pytest.mark.matrix_case(case_id="UI-ROUTE-006", context_id="route", lane="default")
async def test_pdf_extract_with_files_field_omitted_returns_422(tmp_path: Path) -> None:
    """The multipart 'files' field omitted entirely never reaches the route body at all --
    FastAPI's own validation (list[UploadFile] = File(...) is required) rejects it with 422
    before the handler's own 'if not files' guard ever runs. Mirrors UI-ROUTE-006."""
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/pdf-extract")
    assert resp.status_code == 422


def _fake_pdf_main_blocks_until_released(started: threading.Event, release: threading.Event):
    def fake(argv: list[str], *, progress_callback=None) -> int:
        # pdf_cli.main is invoked via asyncio.to_thread -- a SYNC callable run in a real worker
        # thread -- so this fake blocks with plain threading primitives, never asyncio ones.
        started.set()
        release.wait(timeout=5)
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        return 0

    return fake


@pytest.mark.matrix_case(case_id="UI-ROUTE-007", context_id="route", lane="default")
async def test_pdf_extract_busy_rejects_a_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI-ROUTE-007: while a pdf-extract job is genuinely still in flight (blocked here on a
    real threading.Event so the race with UI-ROUTE-025's fast fake can't hide the assertion),
    a second POST is rejected with 409 without touching pdf_uploads_dir or scheduling a second
    worker."""
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(
        routes_module.pdf_cli, "main", _fake_pdf_main_blocks_until_released(started, release)
    )
    async with _client_for(tmp_path) as (client, _settings):
        resp1 = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp1.status_code == 202
        await asyncio.to_thread(started.wait, 5)

        resp2 = await client.post(
            "/api/pdf-extract", files={"files": ("b.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp2.status_code == 409

        release.set()
        operation_id = resp1.json()["operation_id"]
        await _drain(client, operation_id)


@pytest.mark.matrix_case(case_id="UI-ROUTE-024", context_id="route", lane="default")
async def test_pdf_extract_success_writes_csv_and_frees_job_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        routes_module.pdf_cli, "main", _fake_pdf_main_success(_SCOUTS_CSV_BODY)
    )
    async with _client_for(tmp_path) as (client, settings):
        before = _tasks_snapshot()
        resp = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        task = _only_spawned_task(before)
        await asyncio.wait_for(task, timeout=5)
        events = await _drain(client, operation_id)
        assert events[-1]["type"] == "batch_done"
        assert settings.scouts_csv.exists()

        # job_registry must be free again once the worker finishes -- a second call succeeds.
        resp2 = await client.post(
            "/api/pdf-extract", files={"files": ("b.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp2.status_code == 202


@pytest.mark.matrix_case(case_id="UI-ROUTE-025", context_id="route", lane="default")
async def test_pdf_extract_rejects_concurrent_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_module.pdf_cli, "main", _fake_pdf_main_error("boom-pdf"))
    async with _client_for(tmp_path) as (client, _settings):
        resp1 = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp1.status_code == 202
        resp2 = await client.post(
            "/api/pdf-extract", files={"files": ("b.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp2.status_code == 409
        operation_id = resp1.json()["operation_id"]
        events = await _drain(client, operation_id)
        assert events[0]["type"] == "error"
        assert events[0]["message"] == "boom-pdf"


@pytest.mark.matrix_case(case_id="UI-ROUTE-026", context_id="route", lane="default")
async def test_schedule_download_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_module, "run_schedule", _fake_schedule_async_main(summary_extra={"scouts_processed": 1})
    )
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        before = _tasks_snapshot()
        resp = await client.post("/api/schedule-download")
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        task = _only_spawned_task(before)
        await asyncio.wait_for(task, timeout=5)
        events = await _drain(client, operation_id)
        assert events[-1]["type"] == "batch_done"
        assert events[-1]["scouts_processed"] == 1


@pytest.mark.matrix_case(case_id="UI-ROUTE-027", context_id="route", lane="default")
async def test_schedule_download_worker_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_module, "run_schedule", _fake_schedule_async_main(raise_message="boom-schedule")
    )
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        before = _tasks_snapshot()
        resp = await client.post("/api/schedule-download")
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        task = _only_spawned_task(before)
        await asyncio.wait_for(task, timeout=5)
        events = await _drain(client, operation_id)
        assert events[-1]["type"] == "error"
        assert events[-1]["message"] == "boom-schedule"

        # busy-equivalent state (job_registry) must be free again after a worker error, exactly
        # like the success path -- a second schedule-download is accepted, not rejected as
        # still-running.
        resp2 = await client.post("/api/schedule-download")
        assert resp2.status_code == 202


@pytest.mark.matrix_case(case_id="UI-ROUTE-008", context_id="route", lane="default")
async def test_schedule_download_missing_csv_returns_409(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/schedule-download")
    assert resp.status_code == 409


@pytest.mark.matrix_case(case_id="UI-ROUTE-010", context_id="route", lane="default")
async def test_pause_inactive_returns_409(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        pause_resp = await client.post("/api/schedule-download/pause")
    assert pause_resp.status_code == 409


@pytest.mark.matrix_case(case_id="UI-ROUTE-012", context_id="route", lane="default")
async def test_resume_inactive_returns_409(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resume_resp = await client.post("/api/schedule-download/resume")
    assert resume_resp.status_code == 409


def _fake_schedule_async_main_blocks_until_released(release: asyncio.Event):
    """A schedule-download worker that stays 'running' (job_registry still shows it as pending)
    until the test explicitly releases it -- lets a test exercise the busy/pause/resume-while-
    active routes against a REAL in-flight job via real HTTP calls, mirroring UI-ROUTE-009/011/013."""

    async def fake(config, *, progress_callback=None, resume_event=None) -> int:
        await release.wait()
        config.output.mkdir(parents=True, exist_ok=True)
        (config.output / "summary.json").write_text(
            json.dumps({"scouts_processed": 0, "scouts_with_errors": 0, "html_report": None}),
            encoding="utf-8",
        )
        return 0

    return fake


@pytest.mark.matrix_case(case_id="UI-ROUTE-009", context_id="route", lane="default")
async def test_schedule_download_busy_rejects_a_second_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    monkeypatch.setattr(
        routes_module, "run_schedule", _fake_schedule_async_main_blocks_until_released(release)
    )
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        resp1 = await client.post("/api/schedule-download")
        assert resp1.status_code == 202
        resp2 = await client.post("/api/schedule-download")
        assert resp2.status_code == 409
        release.set()
        operation_id = resp1.json()["operation_id"]
        await _drain(client, operation_id)


@pytest.mark.matrix_case(case_id="UI-ROUTE-011", context_id="route", lane="default")
async def test_pause_while_active_returns_paused_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    monkeypatch.setattr(
        routes_module, "run_schedule", _fake_schedule_async_main_blocks_until_released(release)
    )
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        resp = await client.post("/api/schedule-download")
        assert resp.status_code == 202
        pause_resp = await client.post("/api/schedule-download/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json() == {"paused": True}
        release.set()
        operation_id = resp.json()["operation_id"]
        await _drain(client, operation_id)


@pytest.mark.matrix_case(case_id="UI-ROUTE-013", context_id="route", lane="default")
async def test_resume_while_active_returns_paused_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    monkeypatch.setattr(
        routes_module, "run_schedule", _fake_schedule_async_main_blocks_until_released(release)
    )
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        resp = await client.post("/api/schedule-download")
        assert resp.status_code == 202
        resume_resp = await client.post("/api/schedule-download/resume")
        assert resume_resp.status_code == 200
        assert resume_resp.json() == {"paused": False}
        release.set()
        operation_id = resp.json()["operation_id"]
        await _drain(client, operation_id)


@pytest.mark.matrix_case(case_id="UI-ROUTE-014", context_id="route", lane="default")
async def test_operation_events_for_unknown_operation_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.get("/api/operations/UNKNOWN-OP/events")
    assert resp.status_code == 404


@pytest.mark.matrix_case(case_id="UI-ROUTE-015", context_id="route", lane="default")
async def test_list_runs_empty(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.matrix_case(case_id="UI-ROUTE-016", context_id="route", lane="default")
async def test_open_report_unknown_run_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/runs/UNKNOWN-RUN/open-report")
    assert resp.status_code == 404


@pytest.mark.matrix_case(case_id="UI-ROUTE-017", context_id="route", lane="default")
async def test_open_report_no_html_report_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text("{}", encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
    assert resp.status_code == 404


@pytest.mark.matrix_case(case_id="UI-ROUTE-018", context_id="route", lane="default")
async def test_open_report_success_calls_webbrowser_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(routes_module.webbrowser, "open", lambda url: opened.append(url))
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
        (run_dir / "summary.json").write_text(
            json.dumps({"html_report": "report.html"}), encoding="utf-8"
        )
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
    assert resp.status_code == 200
    assert resp.json()["opened"] is True
    assert opened


@pytest.mark.matrix_case(case_id="UI-ROUTE-030", context_id="route", lane="default")
async def test_open_report_rejects_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(routes_module.webbrowser, "open", lambda url: opened.append(url))
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(
            json.dumps({"html_report": "../../elsewhere/evil.html"}), encoding="utf-8"
        )
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
    assert resp.status_code == 400
    assert not opened


async def test_open_report_corrupt_summary_returns_400(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text("{not valid json", encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
    assert resp.status_code == 400


@pytest.mark.matrix_case(case_id="UI-ROUTE-019", context_id="route", lane="default")
async def test_generate_emails_missing_scouts_json_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/runs/UNKNOWN-RUN/generate-emails")
    assert resp.status_code == 404


@pytest.mark.matrix_case(case_id="UI-ROUTE-020", context_id="route", lane="default")
async def test_generate_emails_success_returns_real_counts(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        scouts = [
            {
                "name": "Avery Archer",
                "attendee_id": "90000001",
                "classes": [],
                "errors": [],
                "requirements": [
                    {
                        "scout_name": "Avery Archer",
                        "attendee_id": "90000001",
                        "class_p4_id": "1",
                        "class_number": "26MB1",
                        "merit_badge_name": "Chess",
                        "requirement_id": "r1",
                        "requirement_type_id": "1",
                        "requirement_number": "#1",
                        "description": "Show up.",
                        "completed_requirement": False,
                        "completed_class": False,
                        "requirement_on_event": True,
                        "present_days": "",
                    }
                ],
            }
        ]
        (run_dir / "scouts.json").write_text(json.dumps(scouts), encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/generate-emails")
    assert resp.status_code == 200
    assert resp.json() == {
        "generated": True,
        "scouts_needing_email": 1,
        "scouts_all_complete": 0,
        "scouts_no_data": 0,
    }


@pytest.mark.matrix_case(case_id="UI-ROUTE-021", context_id="route", lane="default")
async def test_generate_emails_corrupt_scouts_json_returns_500(tmp_path: Path) -> None:
    # UI-ROUTE-021 is a PRESERVE case: generate_emails's scouts.json read is deliberately
    # left unguarded on the legacy app, and the package route mirrors that exact behavior.
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "scouts.json").write_text("{not valid json", encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/generate-emails")
    assert resp.status_code == 500


@pytest.mark.matrix_case(case_id="UI-ROUTE-022", context_id="route", lane="default")
async def test_open_emails_folder_missing_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/runs/UNKNOWN-RUN/open-emails-folder")
    assert resp.status_code == 404


@pytest.mark.matrix_case(case_id="UI-ROUTE-023", context_id="route", lane="default")
async def test_open_emails_folder_success_calls_open_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened_paths: list[str] = []
    monkeypatch.setattr(
        routes_module, "open_folder", lambda path: opened_paths.append(str(path))
    )
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        (run_dir / "emails").mkdir(parents=True)
        resp = await client.post("/api/runs/2026-07-23_1200/open-emails-folder")
    assert resp.status_code == 200
    assert resp.json() == {"opened": True}
    assert opened_paths


async def test_root_serves_the_frontend(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.matrix_case(case_id="UI-ROUTE-028", context_id="route", lane="default")
async def test_events_success_full_drain_removes_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI-ROUTE-028: a real operation driven to completion returns 200 text/event-stream, and
    once the real body_iterator is fully drained the operation_id is gone from
    app.state.operations (the generator's own `finally` clause, ui/server.py:310-311's package
    equivalent)."""
    monkeypatch.setattr(routes_module.pdf_cli, "main", _fake_pdf_main_success(_SCOUTS_CSV_BODY))
    settings = UiSettings(data_root=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
            )
            assert resp.status_code == 202
            operation_id = resp.json()["operation_id"]

            async with client.stream(
                "GET", f"/api/operations/{operation_id}/events"
            ) as stream_resp:
                assert stream_resp.status_code == 200
                assert "text/event-stream" in stream_resp.headers["content-type"]
                async for _ in stream_resp.aiter_lines():
                    pass  # drain fully -- the None sentinel ends the generator naturally

            assert operation_id not in app.state.operations


@pytest.mark.matrix_case(case_id="UI-ROUTE-029", context_id="route", lane="default")
async def test_events_disconnect_removes_operation_before_worker_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing the SSE stream early (simulating a client disconnect) still runs the route
    generator's own `finally: operations.pop(...)` -- the operation_id is removed immediately,
    even though the underlying worker task (unrelated to this generator) keeps running to its
    own completion. Mirrors UI-ROUTE-029's legacy contract."""

    started = threading.Event()
    release = threading.Event()

    def fake_pdf_main(argv: list[str], *, progress_callback=None) -> int:
        # pdf_cli.main is called via asyncio.to_thread -- a SYNC callable run in a worker
        # thread -- so this fake blocks with plain threading primitives, never asyncio ones.
        started.set()
        release.wait(timeout=5)
        return 0

    monkeypatch.setattr(routes_module.pdf_cli, "main", fake_pdf_main)
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        await asyncio.to_thread(started.wait, 5)

        async with client.stream("GET", f"/api/operations/{operation_id}/events") as stream:
            async for _ in stream.aiter_lines():
                break  # consume nothing real, just open the stream then close it

        status_resp = await client.get(f"/api/operations/{operation_id}/events")
        assert status_resp.status_code == 404

        release.set()


@pytest.mark.parametrize(("case", "context_id"), execution_params(INTERFACE_CASES_METHOD))
async def test_wrong_http_method_matches_legacy(tmp_path: Path, case, context_id: str) -> None:
    """Mirrors UI-METHOD-001..012 (one parametrize instance per case, driven directly off the
    frozen catalog so the expected status/body can never drift from what interface_cases.py
    pins): a GET against a POST-only route is swallowed by the catch-all `/` static mount
    (registered last) before Starlette's router ever reports a method mismatch, surfacing as 404
    'Not Found' rather than 405 -- the exact same ordering quirk `ui/server.py` has, since
    create_app registers routes before static mounts too. A POST against a GET-only route
    reaches the real router, which returns a genuine 405."""
    expected = case.expected_by_context[context_id]
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.request(case.method, case.route)
    assert response.status_code == expected.status
    if expected.body is not None:
        assert response.json() == expected.body


# --------------------------------------------------------------------------------------------
# Package equivalents of tests/characterization/test_phase_a_gap_closure.py's ui/server.py-
# specific gap-closure tests (deleted alongside ui/server.py in B10.3): _safe_run_id's second
# check, _new_run_id's real collision loop, an empty file list reaching start_pdf_extract's own
# guard directly (unreachable via a real HTTP client -- see UI-ROUTE-006's docstring, which
# applies identically here), and the stale-uploads-cleanup/warnings-count branches.
# --------------------------------------------------------------------------------------------
def test_safe_run_id_rejects_a_bare_dot_via_the_resolved_parent_check(tmp_path: Path) -> None:
    """"." contains none of '/', '\\\\', '..' (the first guard), but runs_dir/"." resolves to
    runs_dir itself, whose parent is runs_dir's parent, not runs_dir -- exactly the mismatch the
    second check exists to catch."""
    from fastapi import HTTPException

    settings = UiSettings(data_root=tmp_path)
    with pytest.raises(HTTPException) as excinfo:
        routes_module._safe_run_id(settings, ".")
    assert excinfo.value.status_code == 400


def test_new_run_id_appends_a_numeric_suffix_on_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = UiSettings(data_root=tmp_path)
    settings.ensure_dirs()
    fixed = "2026-07-24_1200"
    monkeypatch.setattr(routes_module.time, "strftime", lambda fmt: fixed)
    (settings.runs_dir / fixed).mkdir(parents=True)
    assert routes_module._new_run_id(settings) == f"{fixed}-2"
    (settings.runs_dir / f"{fixed}-2").mkdir(parents=True)
    assert routes_module._new_run_id(settings) == f"{fixed}-3"


def _fake_request_for(settings: UiSettings):
    from types import SimpleNamespace

    from scoutmb.runtime.jobs import JobSupervisor

    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings, job_registry=JobSupervisor(), operations={}
            )
        )
    )


async def test_start_pdf_extract_rejects_an_empty_file_list_when_called_directly(
    tmp_path: Path,
) -> None:
    """Reaching the route's own "if not files" guard requires calling the function directly
    with files=[] -- FastAPI's own validation always rejects an entirely-omitted field with 422
    first when driven through a real client (see UI-ROUTE-006/
    test_pdf_extract_with_files_field_omitted_returns_422), so this branch is otherwise dead."""
    settings = UiSettings(data_root=tmp_path)
    request = _fake_request_for(settings)
    with pytest.raises(routes_module.HTTPException) as excinfo:
        await routes_module.start_pdf_extract(request, files=[])
    assert excinfo.value.status_code == 400


async def test_pdf_extract_cleans_stale_uploads_and_counts_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-seeds pdf_uploads_dir with a stale file from a prior run (the is_file()-guarded
    cleanup branch) and makes pdf_cli.main write an errors CSV so the worker's warnings count is
    exercised, not just its errors.exists()-is-False path."""

    def fake_main(argv: list[str], *, progress_callback=None) -> int:
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text(
            "Attendee Name,Registrant Type,QR Code Contents\r\n"
            "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n",
            encoding="utf-8-sig",
        )
        errors_csv = out_path.with_name(f"{out_path.stem}.errors.csv")
        errors_csv.write_text(
            "scout_name,attendee_id,error\r\nSomeone,123,boom\r\n", encoding="utf-8-sig"
        )
        return 1

    monkeypatch.setattr(routes_module.pdf_cli, "main", fake_main)
    async with _client_for(tmp_path) as (client, settings):
        settings.pdf_uploads_dir.mkdir(parents=True)
        stale = settings.pdf_uploads_dir / "old-upload.pdf"
        stale.write_bytes(b"stale")

        before = _tasks_snapshot()
        resp = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        task = _only_spawned_task(before)
        await asyncio.wait_for(task, timeout=5)
        events = await _drain(client, operation_id)

        assert not stale.exists()  # the stale upload was cleaned up before the new one was saved
        batch_done = next(event for event in events if event["type"] == "batch_done")
        assert batch_done["warnings"] == 1


# --------------------------------------------------------------------------------------------
# RUN-ID-001..004 -- _safe_run_id's path-traversal guard, driven directly off the frozen
# catalog's (raw, expected_status) pairs, matching the catalog's own method="CALL" contract
# (calling the function directly rather than through a real HTTP request).
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("case", "context_id"), execution_params(INTERFACE_CASES_RUN_ID))
def test_safe_run_id_matches_the_matrix_catalog(tmp_path: Path, case, context_id: str) -> None:
    raw, expected_status = case.expected_by_context[context_id]
    settings = UiSettings(data_root=tmp_path)
    if expected_status is None:
        result = routes_module._safe_run_id(settings, raw)
        assert result == settings.runs_dir / raw
    else:
        with pytest.raises(routes_module.HTTPException) as excinfo:
            routes_module._safe_run_id(settings, raw)
        assert excinfo.value.status_code == expected_status


# --------------------------------------------------------------------------------------------
# RUN-LIST-001..004 -- GET /api/runs (list_runs).
# --------------------------------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="RUN-LIST-001", context_id="run-list", lane="default")
async def test_run_list_empty_matches_the_matrix_catalog(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.matrix_case(case_id="RUN-LIST-002", context_id="run-list", lane="default")
async def test_run_list_reverse_sorted_multiple(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        for run_id in ("2026-07-23_1200", "2026-07-23_1300"):
            run_dir = settings.runs_dir / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(
                json.dumps({"scouts_processed": 0, "scouts_with_errors": 0}), encoding="utf-8"
            )
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    assert [row["run_id"] for row in resp.json()] == ["2026-07-23_1300", "2026-07-23_1200"]


@pytest.mark.matrix_case(case_id="RUN-LIST-003", context_id="run-list", lane="default")
async def test_run_list_corrupt_summary_ignored(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text("{not valid json", encoding="utf-8")
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.matrix_case(case_id="RUN-LIST-004", context_id="run-list", lane="default")
async def test_run_list_missing_optional_report(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(
            json.dumps({"scouts_processed": 0, "scouts_with_errors": 0}), encoding="utf-8"
        )
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert [row["run_id"] for row in body] == ["2026-07-23_1200"]
    assert body[0]["report_url"] is None


# --------------------------------------------------------------------------------------------
# SSE-FRAME-001..006 -- the real ordered sequence of SSE frames a schedule-download operation
# yields, for zero-scout / single-scout / pause-resume / multi-scout / mid-batch-exception /
# non-fatal-per-scout-error scenarios. Driven through the REAL queue + REAL event_stream()
# generator (never a hand-built wire-format string); run_schedule is narrowly monkeypatched at
# the exact call boundary the real worker uses, and the SCRIPTED events it replays via
# progress_callback are derived directly from the catalog's own expected frames -- so the fake
# can never drift from what interface_cases.py pins.
# --------------------------------------------------------------------------------------------
def _fake_schedule_from_sse_case(case):
    frames = case.expected_by_context["sse-frame"].frames
    scripted = frames[:-1]  # "batch_done"/"error" is constructed by the ROUTE, not run_schedule
    last = frames[-1]

    async def fake(config, *, progress_callback=None, resume_event=None) -> int:
        for event in scripted:
            if progress_callback is not None:
                await progress_callback(dict(event))
        if last["type"] == "error":
            raise RuntimeError(last["message"])
        config.output.mkdir(parents=True, exist_ok=True)
        summary = {
            "scouts_processed": last["scouts_processed"],
            "scouts_with_errors": last["scouts_with_errors"],
            "html_report": None,
        }
        (config.output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return 0

    return fake


@pytest.mark.parametrize(("case", "context_id"), execution_params(SSE_FRAME_CASES))
async def test_sse_frame_sequence_matches_the_matrix_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case, context_id: str
) -> None:
    expected = case.expected_by_context[context_id]
    monkeypatch.setattr(routes_module, "run_schedule", _fake_schedule_from_sse_case(case))
    monkeypatch.setattr(routes_module, "_new_run_id", lambda settings: SSE_FIXED_RUN_ID)
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        resp = await client.post("/api/schedule-download")
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        events = await _drain(client, operation_id)
    assert tuple(event["type"] for event in events) == expected.frame_types
    assert tuple(events) == tuple(dict(frame) for frame in expected.frames)


# --------------------------------------------------------------------------------------------
# SSE-CLEAN-001..004 -- lifecycle cleanup of operations/job_registry/current_download plus the
# background asyncio task, for success, worker-exception, terminal-attendee-failure, and
# client-disconnect. Deliberately schedule-download-specific (not pdf-extract, which has no
# current_download state at all) -- constructs the app directly (rather than via _client_for)
# so app.state.operations/job_registry/current_download stay reachable for assertion.
#
# The disconnect scenario does NOT go through httpx/ASGITransport for the events request:
# httpx's ASGITransport (see handle_async_request in httpx/_transports/asgi.py) drives the
# whole ASGI app call to full completion internally BEFORE ever returning a Response object --
# it is not lazily streaming despite the name -- so client.stream() cannot observe a real
# operation whose body_iterator would otherwise never finish on its own. Instead this calls
# routes_module.operation_events(...) directly to obtain the real StreamingResponse, then
# cancels the task driving its body_iterator's first __anext__() right at its 'await
# queue.get()' suspension point -- the same underlying try/finally unwind a real client
# disconnect's aclose() drives in Starlette's own body_iterator consumption.
# --------------------------------------------------------------------------------------------
async def _observe_sse_clean_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_run_schedule,
    *,
    disconnect: bool,
    release_after_disconnect: asyncio.Event | None = None,
) -> SseCleanObservation:
    settings = UiSettings(data_root=tmp_path)
    monkeypatch.setattr(routes_module, "run_schedule", fake_run_schedule)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
            resp = await client.post("/api/schedule-download")
            assert resp.status_code == 202
            operation_id = resp.json()["operation_id"]
            task = app.state.job_registry.get("schedule-download")
            assert task is not None

            if disconnect:
                from types import SimpleNamespace

                fake_request = SimpleNamespace(app=app)
                response = await routes_module.operation_events(fake_request, operation_id)
                agen = response.body_iterator
                first_next = asyncio.ensure_future(agen.__anext__())
                await asyncio.sleep(0)  # let the generator reach its 'await queue.get()' suspend
                assert not first_next.done(), "the generator must genuinely be waiting on the queue"
                first_next.cancel()
                with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                    await first_next

                operation_removed = operation_id not in app.state.operations
                assert operation_removed, (
                    "the generator's own 'finally' must remove the operation immediately on "
                    "disconnect, before the still-running background worker is ever released"
                )
                assert release_after_disconnect is not None
                release_after_disconnect.set()  # now let the detached worker finish on its own
            else:
                await _drain(client, operation_id)
                operation_removed = operation_id not in app.state.operations

            await asyncio.wait_for(task, timeout=5)

            observation = SseCleanObservation(
                operation_removed=operation_removed,
                busy_reset=app.state.job_registry.get("schedule-download") is None,
                current_download_cleared=app.state.current_download == {},
                task_done=task.done(),
            )
    return observation


def _sse_clean_case(case_id: str):
    return next(case for case in SSE_CLEAN_CASES if case.meta.case_id == case_id)


@pytest.mark.matrix_case(case_id="SSE-CLEAN-001", context_id="sse-clean", lane="default")
async def test_sse_clean_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed = await _observe_sse_clean_scenario(
        tmp_path,
        monkeypatch,
        _fake_schedule_async_main(summary_extra={"scouts_processed": 1}),
        disconnect=False,
    )
    assert observed == _sse_clean_case("SSE-CLEAN-001").expected_by_context["sse-clean"]


@pytest.mark.matrix_case(case_id="SSE-CLEAN-002", context_id="sse-clean", lane="default")
async def test_sse_clean_worker_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed = await _observe_sse_clean_scenario(
        tmp_path,
        monkeypatch,
        _fake_schedule_async_main(raise_message="boom-schedule-clean"),
        disconnect=False,
    )
    assert observed == _sse_clean_case("SSE-CLEAN-002").expected_by_context["sse-clean"]


@pytest.mark.matrix_case(case_id="SSE-CLEAN-003", context_id="sse-clean", lane="default")
async def test_sse_clean_terminal_attendee_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = await _observe_sse_clean_scenario(
        tmp_path,
        monkeypatch,
        _fake_schedule_async_main(summary_extra={"scouts_processed": 1, "scouts_with_errors": 1}),
        disconnect=False,
    )
    assert observed == _sse_clean_case("SSE-CLEAN-003").expected_by_context["sse-clean"]


@pytest.mark.matrix_case(case_id="SSE-CLEAN-004", context_id="sse-clean", lane="default")
async def test_sse_clean_client_disconnect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = asyncio.Event()
    observed = await _observe_sse_clean_scenario(
        tmp_path,
        monkeypatch,
        _fake_schedule_async_main_blocks_until_released(release),
        disconnect=True,
        release_after_disconnect=release,
    )
    assert observed == _sse_clean_case("SSE-CLEAN-004").expected_by_context["sse-clean"]
