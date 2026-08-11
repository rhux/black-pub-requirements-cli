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
    assert "<html" in response.text.lower()
