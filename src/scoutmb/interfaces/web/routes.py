"""Package-side route handlers. Imports features/ports/core only -- never an adapter directly
(scoutmb.interfaces.web.composition is the sole adapter-importing module in this package,
enforced by the architecture test). Registered onto the app by create_app().

pdf-extract uses scoutmb.interfaces.cli.pdf.main -- the real, package-native implementation
pdf_to_scouts.main is now just a compatibility shim re-exporting (same function object,
confirmed by reading pdf_to_scouts.py's own docstring) -- never the flat pdf_to_scouts module
itself, which tests/compat/test_legacy_entrypoints.py's test_package_never_imports_the_flat_pdf_module
bans anywhere under src/scoutmb.

schedule-download still delegates to the top-level scout_schedule_cli module, exactly as
ui/server.py does -- its package-native replacement doesn't exist yet (Slice 2b sub-plan 4's
job; sub-plan 1 built AcquisitionService as an additive, parity-tested unit, not yet the thing
async_main calls). scout_schedule_cli is not part of the scoutmb.* layered package, so importing
it here does not create a cross-layer edge the architecture test tracks. State that ui/server.py
keeps in module globals (busy/operations/current_download) is kept in app.state instead, with
"is a job currently running" tracked via app.state.job_registry (a JobSupervisor) rather than a
bare busy dict.

No sys.path/__file__ bootstrap here (tests/architecture bans both anywhere in src/scoutmb) --
scout_schedule_cli imports successfully because the process that runs this module already has
the repo root on sys.path (pytest's own rootdir insertion during tests; ui/server.py's explicit
insertion in production). A troop349-schedule console-script run from outside the repo, with
neither of those already true, is out of scope for this sub-plan -- resolved when sub-plan 4
retires the flat script in favor of a fully package-native equivalent."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import scout_schedule_cli
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from scoutmb.config import ScheduleConfig, UiSettings
from scoutmb.interfaces.cli import pdf as pdf_cli

router = APIRouter()


def _safe_run_id(settings: UiSettings, run_id: str) -> Path:
    runs_dir = settings.runs_dir
    if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(400, "Invalid run id")
    run_dir = runs_dir / run_id
    if run_dir.resolve().parent != runs_dir.resolve():
        raise HTTPException(400, "Invalid run id")
    return run_dir


def open_folder(path: Path) -> None:
    """Cross-platform 'reveal in file manager'. A module-level function (not inlined into the
    route) so tests can monkeypatch it instead of launching a real GUI window."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - local-only app, user-triggered
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _safe_report_path(run_dir: Path, html_report: str) -> Path | None:
    """None if html_report is not a bare filename resolving inside run_dir -- never lets an
    unvalidated persisted string reach webbrowser.open."""
    candidate = Path(html_report)
    if not html_report or candidate.name != html_report:
        return None
    resolved = (run_dir / html_report).resolve()
    if resolved.parent != run_dir.resolve():
        return None
    if not resolved.is_file():
        return None
    return resolved


def _read_scouts_rows(settings: UiSettings) -> list[dict[str, str]]:
    with settings.scouts_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _new_run_id(settings: UiSettings) -> str:
    runs_dir = settings.runs_dir
    base = time.strftime("%Y-%m-%d_%H%M")
    candidate = base
    suffix = 2
    while (runs_dir / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@router.get("/api/status")
async def get_status(request: Request) -> dict[str, Any]:
    settings: UiSettings = request.app.state.settings
    if not settings.scouts_csv.exists():
        return {"scouts_csv_exists": False, "scouts_count": None, "scouts_mtime": None}
    rows = _read_scouts_rows(settings)
    mtime = datetime.fromtimestamp(settings.scouts_csv.stat().st_mtime).isoformat(
        timespec="seconds"
    )
    return {"scouts_csv_exists": True, "scouts_count": len(rows), "scouts_mtime": mtime}


@router.get("/api/scouts")
async def get_scouts(request: Request) -> list[dict[str, str]]:
    settings: UiSettings = request.app.state.settings
    if not settings.scouts_csv.exists():
        raise HTTPException(404, "scouts.csv not found")
    rows = _read_scouts_rows(settings)
    return [
        {
            "name": row.get("Attendee Name", "") or "",
            "registrant_type": row.get("Registrant Type", "") or "",
        }
        for row in rows
    ]


@router.post("/api/pdf-extract", status_code=202)
async def start_pdf_extract(
    request: Request, files: list[UploadFile] = File(...)
) -> JSONResponse:
    settings: UiSettings = request.app.state.settings
    job_registry = request.app.state.job_registry
    if not files:
        raise HTTPException(400, "No files uploaded")
    if job_registry.get("pdf-extract") is not None:
        raise HTTPException(409, "A PDF extraction is already running")

    operation_id = str(uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.operations[operation_id] = queue

    pdf_uploads_dir = settings.pdf_uploads_dir
    if pdf_uploads_dir.exists():
        for stale in pdf_uploads_dir.iterdir():
            if stale.is_file():
                stale.unlink()
    else:
        pdf_uploads_dir.mkdir(parents=True)

    saved_paths: list[Path] = []
    for upload in files:
        dest = pdf_uploads_dir / Path(upload.filename or "upload.pdf").name
        dest.write_bytes(await upload.read())
        saved_paths.append(dest)

    loop = asyncio.get_running_loop()

    def on_progress(index: int, total: int, pdf_path: Path) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "pdf_start", "index": index, "total": total, "path": pdf_path.name},
        )

    async def worker() -> None:
        try:
            argv = [str(path) for path in saved_paths] + ["-o", str(settings.scouts_csv)]
            return_code = await asyncio.to_thread(
                pdf_cli.main, argv, progress_callback=on_progress
            )
            rows = _read_scouts_rows(settings) if settings.scouts_csv.exists() else []
            decoded_count = sum(1 for row in rows if row.get("QR Code Contents"))
            errors_csv = settings.scouts_csv.with_name(f"{settings.scouts_csv.stem}.errors.csv")
            warnings = 0
            if errors_csv.exists():
                with errors_csv.open("r", encoding="utf-8-sig", newline="") as stream:
                    warnings = sum(1 for _ in csv.DictReader(stream))
            await queue.put(
                {
                    "type": "batch_done",
                    "rows_written": len(rows),
                    "decoded_count": decoded_count,
                    "warnings": warnings,
                    "return_code": return_code,
                }
            )
        except Exception as exc:  # surfaced to the UI, batch does not crash the server
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    job_registry.start("pdf-extract", worker())
    return JSONResponse({"operation_id": operation_id}, status_code=202)


@router.post("/api/schedule-download", status_code=202)
async def start_schedule_download(request: Request) -> JSONResponse:
    settings: UiSettings = request.app.state.settings
    job_registry = request.app.state.job_registry
    if not settings.scouts_csv.exists():
        raise HTTPException(409, "scouts.csv not found — upload PDFs first")
    if job_registry.get("schedule-download") is not None:
        raise HTTPException(409, "A schedule download is already running")

    operation_id = str(uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.operations[operation_id] = queue
    run_id = _new_run_id(settings)
    run_dir = settings.runs_dir / run_id
    resume_event = asyncio.Event()
    resume_event.set()
    request.app.state.current_download["resume_event"] = resume_event

    async def on_progress(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            browser_channel = os.environ.get("SCOUTMB_BROWSER_CHANNEL") or None
            config = ScheduleConfig(
                input=settings.scouts_csv,
                sheet="Scouts Only",
                output=run_dir,
                headed=False,
                timeout=45,
                request_delay_ms=200,
                scout_delay_ms=None,
                allow_dead_assets=False,
                include_adults=False,
                no_html=False,
                html_name="report.html",
                channel=browser_channel,
                email_report=False,
            )
            await scout_schedule_cli.async_main(
                config, progress_callback=on_progress, resume_event=resume_event
            )
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            report_name = summary.get("html_report")
            await queue.put(
                {
                    "type": "batch_done",
                    "run_id": run_id,
                    "scouts_processed": summary.get("scouts_processed"),
                    "scouts_with_errors": summary.get("scouts_with_errors"),
                    "report_url": f"/runs/{run_id}/{report_name}" if report_name else None,
                }
            )
        except Exception as exc:  # surfaced to the UI, batch does not crash the server
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)
            request.app.state.current_download.clear()

    job_registry.start("schedule-download", worker())
    return JSONResponse({"operation_id": operation_id, "run_id": run_id}, status_code=202)


@router.post("/api/schedule-download/pause")
async def pause_schedule_download(request: Request) -> dict[str, Any]:
    job_registry = request.app.state.job_registry
    resume_event = request.app.state.current_download.get("resume_event")
    if job_registry.get("schedule-download") is None or resume_event is None:
        raise HTTPException(409, "No schedule download is currently running")
    resume_event.clear()
    return {"paused": True}


@router.post("/api/schedule-download/resume")
async def resume_schedule_download(request: Request) -> dict[str, Any]:
    job_registry = request.app.state.job_registry
    resume_event = request.app.state.current_download.get("resume_event")
    if job_registry.get("schedule-download") is None or resume_event is None:
        raise HTTPException(409, "No schedule download is currently running")
    resume_event.set()
    return {"paused": False}


@router.get("/api/operations/{operation_id}/events")
async def operation_events(request: Request, operation_id: str) -> StreamingResponse:
    operations: dict[str, asyncio.Queue] = request.app.state.operations
    queue = operations.get(operation_id)
    if queue is None:
        raise HTTPException(404, "Unknown operation")

    async def event_stream():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            operations.pop(operation_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/api/runs")
async def list_runs(request: Request) -> list[dict[str, Any]]:
    settings: UiSettings = request.app.state.settings
    runs: list[dict[str, Any]] = []
    for summary_path in settings.runs_dir.glob("*/summary.json"):
        run_id = summary_path.parent.name
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        report_name = summary.get("html_report")
        runs.append(
            {
                "run_id": run_id,
                "generated_at_local": summary.get("generated_at_local"),
                "generated_at_iso": summary.get("generated_at_iso"),
                "scouts_processed": summary.get("scouts_processed"),
                "scouts_with_errors": summary.get("scouts_with_errors"),
                "classes": summary.get("classes"),
                "requirements": summary.get("requirements"),
                "report_url": f"/runs/{run_id}/{report_name}" if report_name else None,
            }
        )
    runs.sort(key=lambda run: run["run_id"], reverse=True)
    return runs


@router.post("/api/runs/{run_id}/open-report")
async def open_report(run_id: str, request: Request) -> dict[str, Any]:
    settings: UiSettings = request.app.state.settings
    run_dir = _safe_run_id(settings, run_id)
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise HTTPException(404, "Run not found")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "This run's summary.json is corrupt") from exc
    report_name = summary.get("html_report")
    if not report_name:
        raise HTTPException(404, "This run has no HTML report")
    if _safe_report_path(run_dir, report_name) is None:
        raise HTTPException(400, "This run's recorded report filename is invalid")
    url = f"{request.base_url}runs/{run_id}/{report_name}"
    webbrowser.open(url)
    return {"opened": True, "url": url}


@router.post("/api/runs/{run_id}/generate-emails")
async def generate_emails(run_id: str, request: Request) -> dict[str, Any]:
    settings: UiSettings = request.app.state.settings
    run_dir = _safe_run_id(settings, run_id)
    scouts_json = run_dir / "scouts.json"
    if not scouts_json.exists():
        raise HTTPException(404, "Run not found or has no scouts.json")
    scouts = json.loads(scouts_json.read_text(encoding="utf-8"))

    await asyncio.to_thread(scout_schedule_cli.write_email_reports, run_dir, scouts)

    with (run_dir / "emails" / "missing_requirements.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    scouts_needing_email = sum(1 for row in rows if row.get("status") == "missing_requirements")
    return {
        "generated": True,
        "scouts_needing_email": scouts_needing_email,
        "scouts_all_complete": sum(1 for row in rows if row.get("status") == "all_complete"),
        "scouts_no_data": sum(1 for row in rows if row.get("status") == "no_data_scraped"),
    }


@router.post("/api/runs/{run_id}/open-emails-folder")
async def open_emails_folder(run_id: str, request: Request) -> dict[str, Any]:
    settings: UiSettings = request.app.state.settings
    run_dir = _safe_run_id(settings, run_id)
    emails_dir = run_dir / "emails"
    if not emails_dir.exists():
        raise HTTPException(404, "Emails have not been generated yet for this run")
    await asyncio.to_thread(open_folder, emails_dir)
    return {"opened": True}
