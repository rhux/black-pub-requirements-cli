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
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

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


async def test_health_route_matches(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_scouts_csv_missing_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/api/scouts")
    assert response.status_code == 404


async def test_status_route_reports_no_csv(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "scouts_csv_exists": False,
        "scouts_count": None,
        "scouts_mtime": None,
    }


async def test_status_and_scouts_report_real_csv(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        settings.scouts_csv.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
        status_resp = await client.get("/api/status")
        scouts_resp = await client.get("/api/scouts")
    assert status_resp.status_code == 200
    assert status_resp.json()["scouts_csv_exists"] is True
    assert status_resp.json()["scouts_count"] == 1
    assert scouts_resp.status_code == 200
    assert scouts_resp.json() == [{"name": "Avery Archer", "registrant_type": "Youth"}]


async def test_pdf_extract_with_files_field_omitted_returns_422(tmp_path: Path) -> None:
    """The multipart 'files' field omitted entirely never reaches the route body at all --
    FastAPI's own validation (list[UploadFile] = File(...) is required) rejects it with 422
    before the handler's own 'if not files' guard ever runs. Mirrors UI-ROUTE-006."""
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/pdf-extract")
    assert resp.status_code == 422


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


async def test_schedule_download_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_module.scout_schedule_cli,
        "async_main",
        _fake_schedule_async_main(summary_extra={"scouts_processed": 1}),
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


async def test_schedule_download_worker_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_module.scout_schedule_cli,
        "async_main",
        _fake_schedule_async_main(raise_message="boom-schedule"),
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


async def test_schedule_download_missing_csv_returns_409(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/schedule-download")
    assert resp.status_code == 409


async def test_schedule_download_pause_resume_require_running_job(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        pause_resp = await client.post("/api/schedule-download/pause")
        resume_resp = await client.post("/api/schedule-download/resume")
    assert pause_resp.status_code == 409
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


async def test_schedule_download_busy_rejects_a_second_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    monkeypatch.setattr(
        routes_module.scout_schedule_cli,
        "async_main",
        _fake_schedule_async_main_blocks_until_released(release),
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


async def test_pause_while_active_returns_paused_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    monkeypatch.setattr(
        routes_module.scout_schedule_cli,
        "async_main",
        _fake_schedule_async_main_blocks_until_released(release),
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


async def test_resume_while_active_returns_paused_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    monkeypatch.setattr(
        routes_module.scout_schedule_cli,
        "async_main",
        _fake_schedule_async_main_blocks_until_released(release),
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


async def test_operation_events_for_unknown_operation_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.get("/api/operations/UNKNOWN-OP/events")
    assert resp.status_code == 404


async def test_list_runs_empty(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_open_report_unknown_run_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/runs/UNKNOWN-RUN/open-report")
    assert resp.status_code == 404


async def test_open_report_no_html_report_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text("{}", encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
    assert resp.status_code == 404


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


async def test_generate_emails_missing_scouts_json_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/runs/UNKNOWN-RUN/generate-emails")
    assert resp.status_code == 404


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


async def test_generate_emails_corrupt_scouts_json_returns_500(tmp_path: Path) -> None:
    # UI-ROUTE-021 is a PRESERVE case: generate_emails's scouts.json read is deliberately
    # left unguarded on the legacy app, and the package route mirrors that exact behavior.
    async with _client_for(tmp_path) as (client, settings):
        run_dir = settings.runs_dir / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "scouts.json").write_text("{not valid json", encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/generate-emails")
    assert resp.status_code == 500


async def test_open_emails_folder_missing_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as (client, _settings):
        resp = await client.post("/api/runs/UNKNOWN-RUN/open-emails-folder")
    assert resp.status_code == 404


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


async def test_events_disconnect_removes_operation_before_worker_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing the SSE stream early (simulating a client disconnect) still runs the route
    generator's own `finally: operations.pop(...)` -- the operation_id is removed immediately,
    even though the underlying worker task (unrelated to this generator) keeps running to its
    own completion. Mirrors UI-ROUTE-029's legacy contract."""
    import threading

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


@pytest.mark.parametrize(
    ("route", "allowed", "wrong"),
    [
        ("/api/health", "GET", "POST"),
        ("/api/status", "GET", "POST"),
        ("/api/scouts", "GET", "POST"),
        ("/api/pdf-extract", "POST", "GET"),
        ("/api/schedule-download", "POST", "GET"),
        ("/api/schedule-download/pause", "POST", "GET"),
        ("/api/schedule-download/resume", "POST", "GET"),
        ("/api/operations/OP-ID/events", "GET", "POST"),
        ("/api/runs", "GET", "POST"),
        ("/api/runs/RUN-ID/open-report", "POST", "GET"),
        ("/api/runs/RUN-ID/generate-emails", "POST", "GET"),
        ("/api/runs/RUN-ID/open-emails-folder", "POST", "GET"),
    ],
)
async def test_wrong_http_method_matches_legacy(
    tmp_path: Path, route: str, allowed: str, wrong: str
) -> None:
    """Mirrors UI-METHOD-001..012: a GET against a POST-only route is swallowed by the
    catch-all `/` static mount (registered last) before Starlette's router ever reports a
    method mismatch, surfacing as 404 'Not Found' rather than 405 -- the exact same ordering
    quirk `ui/server.py` has, since create_app registers routes before static mounts too. A
    POST against a GET-only route reaches the real router, which returns a genuine 405."""
    async with _client_for(tmp_path) as (client, _settings):
        response = await client.request(wrong, route)
    if wrong == "GET":
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
    else:
        assert response.status_code == 405
        assert response.json() == {"detail": "Method Not Allowed"}
