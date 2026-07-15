"""Local FastAPI backend for the Scout schedule pipeline UI.

Wraps pdf_to_scouts.py and scout_schedule_cli.py in-process (no subprocess)
and streams their progress to the frontend over Server-Sent Events. Meant to
be served locally only, either in a browser tab (dev) or inside a pywebview
native window (see run_app.py).
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
import webbrowser
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pdf_to_scouts  # noqa: E402
import scout_schedule_cli  # noqa: E402

from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

SCOUTS_CSV = REPO_ROOT / "scouts.csv"
PDF_UPLOADS_DIR = REPO_ROOT / "pdf-uploads"
RUNS_DIR = REPO_ROOT / "runs"
STATIC_DIR = Path(__file__).resolve().parent / "static"

RUNS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Scouting Merit Badges UI")

operations: dict[str, asyncio.Queue] = {}
busy = {"pdf-extract": False, "schedule-download": False}
current_download: dict[str, Any] = {}


def _safe_run_id(run_id: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(400, "Invalid run id")
    run_dir = RUNS_DIR / run_id
    if run_dir.resolve().parent != RUNS_DIR.resolve():
        raise HTTPException(400, "Invalid run id")
    return run_dir


def read_scouts_rows() -> list[dict[str, str]]:
    with SCOUTS_CSV.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def new_run_id() -> str:
    base = time.strftime("%Y-%m-%d_%H%M")
    candidate = base
    suffix = 2
    while (RUNS_DIR / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    if not SCOUTS_CSV.exists():
        return {"scouts_csv_exists": False, "scouts_count": None, "scouts_mtime": None}
    rows = read_scouts_rows()
    mtime = datetime.fromtimestamp(SCOUTS_CSV.stat().st_mtime).isoformat(timespec="seconds")
    return {"scouts_csv_exists": True, "scouts_count": len(rows), "scouts_mtime": mtime}


@app.get("/api/scouts")
async def get_scouts() -> list[dict[str, str]]:
    if not SCOUTS_CSV.exists():
        raise HTTPException(404, "scouts.csv not found")
    rows = read_scouts_rows()
    return [
        {
            "name": row.get("Attendee Name", "") or "",
            "registrant_type": row.get("Registrant Type", "") or "",
        }
        for row in rows
    ]


@app.post("/api/pdf-extract", status_code=202)
async def start_pdf_extract(files: list[UploadFile] = File(...)) -> JSONResponse:
    if not files:
        raise HTTPException(400, "No files uploaded")
    if busy["pdf-extract"]:
        raise HTTPException(409, "A PDF extraction is already running")
    busy["pdf-extract"] = True

    operation_id = str(uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    operations[operation_id] = queue

    if PDF_UPLOADS_DIR.exists():
        for stale in PDF_UPLOADS_DIR.iterdir():
            stale.unlink()
    else:
        PDF_UPLOADS_DIR.mkdir(parents=True)

    saved_paths: list[Path] = []
    for upload in files:
        dest = PDF_UPLOADS_DIR / Path(upload.filename or "upload.pdf").name
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
            argv = [str(path) for path in saved_paths] + ["-o", str(SCOUTS_CSV)]
            return_code = await asyncio.to_thread(
                pdf_to_scouts.main, argv, progress_callback=on_progress
            )
            rows = read_scouts_rows() if SCOUTS_CSV.exists() else []
            decoded_count = sum(1 for row in rows if row.get("QR Code Contents"))
            errors_csv = SCOUTS_CSV.with_name(f"{SCOUTS_CSV.stem}.errors.csv")
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
            busy["pdf-extract"] = False

    asyncio.create_task(worker())
    return JSONResponse({"operation_id": operation_id}, status_code=202)


@app.post("/api/schedule-download", status_code=202)
async def start_schedule_download() -> JSONResponse:
    if not SCOUTS_CSV.exists():
        raise HTTPException(409, "scouts.csv not found — upload PDFs first")
    if busy["schedule-download"]:
        raise HTTPException(409, "A schedule download is already running")
    busy["schedule-download"] = True

    operation_id = str(uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    operations[operation_id] = queue
    run_id = new_run_id()
    run_dir = RUNS_DIR / run_id
    resume_event = asyncio.Event()
    resume_event.set()
    current_download["resume_event"] = resume_event

    async def on_progress(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            args = Namespace(
                input=SCOUTS_CSV,
                sheet="Scouts Only",
                output=run_dir,
                headed=False,
                timeout=45,
                request_delay_ms=200,
                scout_delay_ms=500,
                allow_dead_assets=False,
                include_adults=False,
                no_html=False,
                html_name="report.html",
            )
            await scout_schedule_cli.async_main(
                args, progress_callback=on_progress, resume_event=resume_event
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
            busy["schedule-download"] = False
            current_download.clear()

    asyncio.create_task(worker())
    return JSONResponse({"operation_id": operation_id, "run_id": run_id}, status_code=202)


@app.post("/api/schedule-download/pause")
async def pause_schedule_download() -> dict[str, Any]:
    resume_event = current_download.get("resume_event")
    if not busy["schedule-download"] or resume_event is None:
        raise HTTPException(409, "No schedule download is currently running")
    resume_event.clear()
    return {"paused": True}


@app.post("/api/schedule-download/resume")
async def resume_schedule_download() -> dict[str, Any]:
    resume_event = current_download.get("resume_event")
    if not busy["schedule-download"] or resume_event is None:
        raise HTTPException(409, "No schedule download is currently running")
    resume_event.set()
    return {"paused": False}


@app.get("/api/operations/{operation_id}/events")
async def operation_events(operation_id: str) -> StreamingResponse:
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


@app.get("/api/runs")
async def list_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for summary_path in RUNS_DIR.glob("*/summary.json"):
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
                "scouts_processed": summary.get("scouts_processed"),
                "scouts_with_errors": summary.get("scouts_with_errors"),
                "classes": summary.get("classes"),
                "requirements": summary.get("requirements"),
                "report_url": f"/runs/{run_id}/{report_name}" if report_name else None,
            }
        )
    runs.sort(key=lambda run: run["run_id"], reverse=True)
    return runs


@app.post("/api/runs/{run_id}/open-report")
async def open_report(run_id: str, request: Request) -> dict[str, Any]:
    run_dir = _safe_run_id(run_id)
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise HTTPException(404, "Run not found")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report_name = summary.get("html_report")
    if not report_name:
        raise HTTPException(404, "This run has no HTML report")
    url = f"{request.base_url}runs/{run_id}/{report_name}"
    webbrowser.open(url)
    return {"opened": True, "url": url}


app.mount("/runs", StaticFiles(directory=RUNS_DIR), name="runs")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
