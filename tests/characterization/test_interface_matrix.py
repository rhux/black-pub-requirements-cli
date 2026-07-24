"""Typed matrix execution of the interface characterization catalog (Task 21).

Every executable ``UI-*`` / ``RUN-*`` case declares one execution context; ``execution_params``
expands them. Every context here drives the REAL ``ui.server`` FastAPI app (never mocked),
reached through ``httpx.AsyncClient`` bound with ``ASGITransport`` -- an in-process ASGI call,
never a real socket -- via the isolated ``tests.harnesses.legacy.load_legacy_ui`` reload
harness so each case gets its own ``tmp_path``-scoped data root.

No test writes outside ``tmp_path`` and this module performs no real file or network I/O.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from tests.harnesses.legacy import load_legacy_ui
from tests.matrix.cases.interface_cases import (
    INTERFACE_CASES,
    SSE_CLEAN_CASES,
    SSE_FRAME_CASES,
    InterfaceCase,
    InterfaceObservation,
    SseCase,
    SseCleanObservation,
    SseFrameObservation,
)
from tests.matrix.pytest_support import execution_params

_FIXED_RUN_ID = "2026-07-24_TEST"
_SCOUTS_CSV_BODY = (
    "Attendee Name,Registrant Type,QR Code Contents\r\n"
    "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n"
)


def _tasks_snapshot() -> set:
    return set(asyncio.all_tasks())


def _only_spawned_task(before: set) -> asyncio.Task:
    spawned = set(asyncio.all_tasks()) - before
    assert len(spawned) == 1, f"expected exactly one spawned worker task, got {spawned}"
    return next(iter(spawned))


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


def _fake_schedule_async_main(
    progress_events: list[dict],
    *,
    summary_extra: dict | None = None,
    raise_message: str | None = None,
):
    async def fake(args, *, progress_callback=None, resume_event=None) -> int:
        for event in progress_events:
            if progress_callback is not None:
                await progress_callback(dict(event))
        if raise_message is not None:
            raise RuntimeError(raise_message)
        args.output.mkdir(parents=True, exist_ok=True)
        summary = {
            "scouts_processed": 0,
            "scouts_with_errors": 0,
            "generated_at_local": "2026-07-24 00:00",
            "generated_at_iso": "2026-07-24T00:00:00",
            "classes": 0,
            "requirements": 0,
            "html_report": None,
            "email_report_dir": None,
        }
        summary.update(summary_extra or {})
        (args.output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return 0

    return fake


def _split_frame_case(frame_case: SseCase) -> tuple[list[dict], dict, str | None]:
    """Pulls a SSE-FRAME case's expected frames apart into: the progress_callback events
    async_main itself would emit (everything except 'batch_done'/'error', which ui/server.py's
    OWN worker constructs, never async_main), the summary.json content the worker needs to have
    on disk to build its own 'batch_done' frame, and the exception message (if any) the fake
    should raise after emitting its progress events."""
    frames = frame_case.expected_by_context["sse-frame"].frames
    progress_events = [dict(frame) for frame in frames if frame["type"] not in ("batch_done", "error")]
    batch_done = next((frame for frame in frames if frame["type"] == "batch_done"), None)
    error = next((frame for frame in frames if frame["type"] == "error"), None)
    summary_extra = (
        {
            "scouts_processed": batch_done["scouts_processed"],
            "scouts_with_errors": batch_done["scouts_with_errors"],
            "html_report": None,
        }
        if batch_done is not None
        else {}
    )
    return progress_events, summary_extra, (error["message"] if error is not None else None)


async def _start_schedule_operation(
    module, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, frame_case: SseCase
) -> tuple[str, asyncio.Task]:
    progress_events, summary_extra, raise_message = _split_frame_case(frame_case)
    fake = _fake_schedule_async_main(
        progress_events, summary_extra=summary_extra, raise_message=raise_message
    )
    monkeypatch.setattr(module.scout_schedule_cli, "async_main", fake)
    monkeypatch.setattr(module, "new_run_id", lambda: _FIXED_RUN_ID)
    module.SCOUTS_CSV.write_text(_SCOUTS_CSV_BODY, encoding="utf-8-sig")
    before = _tasks_snapshot()
    resp = await client.post("/api/schedule-download")
    assert resp.status_code == 202
    operation_id = resp.json()["operation_id"]
    task = _only_spawned_task(before)
    return operation_id, task


async def _drain_via_route(module, operation_id: str) -> tuple[object, list[dict]]:
    """Calls the REAL ``operation_events`` route function directly (it is an ordinary async
    function; the ``@app.get`` decorator does not wrap its body) and iterates the REAL
    ``StreamingResponse.body_iterator`` async generator to completion, parsing each real
    ``data: <json>\\n\\n`` frame back into a dict -- never re-deriving the wire format."""
    resp = await module.operation_events(operation_id)
    events: list[dict] = []
    async for raw_frame in resp.body_iterator:
        payload = raw_frame.removeprefix("data: ").removesuffix("\n\n")
        events.append(json.loads(payload))
    return resp, events


def _client(module) -> httpx.AsyncClient:
    # raise_app_exceptions=False mirrors a real deployed uvicorn server: an unhandled exception
    # inside a route becomes a 500 response, it never crashes the process or propagates out of
    # the client call. UI-ROUTE-021/UI-ROUTE-023 pin exactly this for two routes that currently
    # have no route-level try/except around a call that can raise.
    transport = httpx.ASGITransport(app=module.app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _observe(resp: httpx.Response, *, headers: tuple[tuple[str, str], ...] = ()) -> InterfaceObservation:
    body: object
    try:
        body = resp.json()
    except ValueError:
        body = None
    observed_headers = tuple((k, resp.headers.get(k)) for k, _ in headers)
    return InterfaceObservation(status=resp.status_code, body=body, headers=observed_headers)


class LegacyInterfaceRunner:
    """Runner[InterfaceCase, object] over the real ``ui.server`` FastAPI app."""

    def __init__(self, context_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
        self.context_id = context_id
        self.monkeypatch = monkeypatch

    async def run(self, case: InterfaceCase, *, root: Path) -> object:
        handler = getattr(self, f"_ctx_{self.context_id.replace('-', '_')}")
        return await handler(case, root)

    # -- import ------------------------------------------------------------------------------

    async def _ctx_import(self, case: InterfaceCase, root: Path) -> object:
        if case.meta.case_id == "UI-IMPORT-001":
            data_root = root / "sandbox"
            async with load_legacy_ui(data_root):
                pass
            if not data_root.exists():
                return ()
            return tuple(sorted(p.name for p in data_root.iterdir()))

        # UI-IMPORT-002: a real platform data root would only ever be computed if
        # SCOUTMB_DATA_DIR were unset -- point HOME/LOCALAPPDATA at a decoy under `root` so
        # any accidental write there is observable, while SCOUTMB_DATA_DIR (set by
        # load_legacy_ui) is what the module actually resolves to.
        decoy_home = root / "decoy-home"
        decoy_home.mkdir()
        old_home = os.environ.get("HOME")
        old_lad = os.environ.get("LOCALAPPDATA")
        os.environ["HOME"] = str(decoy_home)
        os.environ["LOCALAPPDATA"] = str(decoy_home)
        try:
            data_root = root / "sandbox2"
            async with load_legacy_ui(data_root):
                pass
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
            if old_lad is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_lad
        return tuple(decoy_home.rglob("*"))

    # -- method (405 contract) ----------------------------------------------------------------

    async def _ctx_method(self, case: InterfaceCase, root: Path) -> object:
        async with load_legacy_ui(root / "data") as module, _client(module) as client:
            resp = await client.request(case.method, case.route)
            return await _observe(resp)

    # -- run-id (pure, no HTTP) ----------------------------------------------------------------

    async def _ctx_run_id(self, case: InterfaceCase, root: Path) -> object:
        expected = case.expected_by_context["run-id"]
        assert isinstance(expected, tuple)
        raw = expected[0]
        async with load_legacy_ui(root / "data") as module:
            try:
                module._safe_run_id(raw)
                return (raw, None)
            except module.HTTPException as exc:
                return (raw, exc.status_code)

    # -- run-list ------------------------------------------------------------------------------

    async def _ctx_run_list(self, case: InterfaceCase, root: Path) -> object:
        async with load_legacy_ui(root / "data") as module:
            member = case.meta.member
            if member == "empty":
                pass
            elif member == "reverse-sorted-multiple":
                self._write_summary(module, "2026-07-23_1200", {"html_report": None})
                self._write_summary(module, "2026-07-23_1300", {"html_report": None})
            elif member == "corrupt-summary-ignored":
                run_dir = module.RUNS_DIR / "2026-07-23_1200"
                run_dir.mkdir(parents=True)
                (run_dir / "summary.json").write_text("{not valid json", encoding="utf-8")
            elif member == "missing-optional-report":
                self._write_summary(module, "2026-07-23_1200", {})
            async with _client(module) as client:
                resp = await client.get("/api/runs")
                body = resp.json()
                return InterfaceObservation(
                    status=resp.status_code, body=[row["run_id"] for row in body]
                )

    @staticmethod
    def _write_summary(module, run_id: str, extra: dict) -> Path:
        run_dir = module.RUNS_DIR / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(json.dumps(extra), encoding="utf-8")
        return run_dir

    # -- route (bespoke per case_id) -------------------------------------------------------------

    async def _ctx_route(self, case: InterfaceCase, root: Path) -> object:
        handler = getattr(self, f"_route_{case.meta.case_id.replace('-', '_')}")
        async with load_legacy_ui(root / "data") as module, _client(module) as client:
            return await handler(module, client)

    async def _route_UI_ROUTE_001(self, module, client) -> InterfaceObservation:
        resp = await client.get("/api/health")
        return await _observe(resp)

    async def _route_UI_ROUTE_002(self, module, client) -> InterfaceObservation:
        resp = await client.get("/api/status")
        return await _observe(resp)

    async def _route_UI_ROUTE_003(self, module, client) -> InterfaceObservation:
        module.SCOUTS_CSV.write_text(
            "Attendee Name,Registrant Type,QR Code Contents\r\n"
            "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n"
            "Bo Baker,Youth,https://scoutingevent.com/mobile/y\r\n",
            encoding="utf-8-sig",
        )
        resp = await client.get("/api/status")
        body = resp.json()
        return InterfaceObservation(
            status=resp.status_code,
            body={"scouts_csv_exists": body["scouts_csv_exists"], "scouts_count": body["scouts_count"]},
        )

    async def _route_UI_ROUTE_004(self, module, client) -> InterfaceObservation:
        resp = await client.get("/api/scouts")
        return await _observe(resp)

    async def _route_UI_ROUTE_005(self, module, client) -> InterfaceObservation:
        module.SCOUTS_CSV.write_text(
            "Attendee Name,Registrant Type,QR Code Contents\r\n"
            "Avery Archer,Youth,https://scoutingevent.com/mobile/x\r\n"
            "Bo Baker,,https://scoutingevent.com/mobile/y\r\n",
            encoding="utf-8-sig",
        )
        resp = await client.get("/api/scouts")
        return await _observe(resp)

    async def _route_UI_ROUTE_006(self, module, client) -> InterfaceObservation:
        # The multipart 'files' field is omitted entirely -- FastAPI's own validation layer
        # rejects this with 422 before the route body's own "if not files" guard ever runs.
        resp = await client.post("/api/pdf-extract")
        return await _observe(resp)

    async def _route_UI_ROUTE_007(self, module, client) -> InterfaceObservation:
        module.busy["pdf-extract"] = True
        try:
            resp = await client.post(
                "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
            )
            return await _observe(resp)
        finally:
            module.busy["pdf-extract"] = False

    async def _route_UI_ROUTE_008(self, module, client) -> InterfaceObservation:
        resp = await client.post("/api/schedule-download")
        return await _observe(resp)

    async def _route_UI_ROUTE_009(self, module, client) -> InterfaceObservation:
        module.SCOUTS_CSV.write_text(
            "Attendee Name,Registrant Type,QR Code Contents\r\n", encoding="utf-8-sig"
        )
        module.busy["schedule-download"] = True
        try:
            resp = await client.post("/api/schedule-download")
            return await _observe(resp)
        finally:
            module.busy["schedule-download"] = False

    async def _route_UI_ROUTE_010(self, module, client) -> InterfaceObservation:
        resp = await client.post("/api/schedule-download/pause")
        return await _observe(resp)

    async def _route_UI_ROUTE_011(self, module, client) -> InterfaceObservation:
        import asyncio

        event = asyncio.Event()
        event.set()
        module.busy["schedule-download"] = True
        module.current_download["resume_event"] = event
        try:
            resp = await client.post("/api/schedule-download/pause")
            observation = await _observe(resp)
            assert event.is_set() is False
            return observation
        finally:
            module.busy["schedule-download"] = False
            module.current_download.clear()

    async def _route_UI_ROUTE_012(self, module, client) -> InterfaceObservation:
        resp = await client.post("/api/schedule-download/resume")
        return await _observe(resp)

    async def _route_UI_ROUTE_013(self, module, client) -> InterfaceObservation:
        import asyncio

        event = asyncio.Event()
        module.busy["schedule-download"] = True
        module.current_download["resume_event"] = event
        try:
            resp = await client.post("/api/schedule-download/resume")
            observation = await _observe(resp)
            assert event.is_set() is True
            return observation
        finally:
            module.busy["schedule-download"] = False
            module.current_download.clear()

    async def _route_UI_ROUTE_014(self, module, client) -> InterfaceObservation:
        resp = await client.get("/api/operations/UNKNOWN-OP/events")
        return await _observe(resp)

    async def _route_UI_ROUTE_015(self, module, client) -> InterfaceObservation:
        resp = await client.get("/api/runs")
        return await _observe(resp)

    async def _route_UI_ROUTE_016(self, module, client) -> InterfaceObservation:
        resp = await client.post("/api/runs/UNKNOWN-RUN/open-report")
        return await _observe(resp)

    async def _route_UI_ROUTE_017(self, module, client) -> InterfaceObservation:
        self._write_summary(module, "2026-07-23_1200", {})
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
        return await _observe(resp)

    async def _route_UI_ROUTE_018(self, module, client) -> InterfaceObservation:
        opened: list[str] = []

        def _record_open(url: str) -> bool:
            opened.append(url)
            return True

        module.webbrowser.open = _record_open
        self._write_summary(module, "2026-07-23_1200", {"html_report": "report.html"})
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
        body = resp.json()
        assert opened, "webbrowser.open was never called"
        return InterfaceObservation(status=resp.status_code, body={"opened": body.get("opened")})

    async def _route_UI_ROUTE_019(self, module, client) -> InterfaceObservation:
        resp = await client.post("/api/runs/UNKNOWN-RUN/generate-emails")
        return await _observe(resp)

    async def _route_UI_ROUTE_020(self, module, client) -> InterfaceObservation:
        run_dir = module.RUNS_DIR / "2026-07-23_1200"
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
        return await _observe(resp)

    async def _route_UI_ROUTE_021(self, module, client) -> InterfaceObservation:
        run_dir = module.RUNS_DIR / "2026-07-23_1200"
        run_dir.mkdir(parents=True)
        (run_dir / "scouts.json").write_text("{not valid json", encoding="utf-8")
        resp = await client.post("/api/runs/2026-07-23_1200/generate-emails")
        return await _observe(resp)

    async def _route_UI_ROUTE_022(self, module, client) -> InterfaceObservation:
        self._write_summary(module, "2026-07-23_1200", {})
        resp = await client.post("/api/runs/2026-07-23_1200/open-emails-folder")
        return await _observe(resp)

    async def _route_UI_ROUTE_023(self, module, client) -> InterfaceObservation:
        run_dir = module.RUNS_DIR / "2026-07-23_1200"
        (run_dir / "emails").mkdir(parents=True)
        resp = await client.post("/api/runs/2026-07-23_1200/open-emails-folder")
        return await _observe(resp)

    async def _route_UI_ROUTE_024(self, module, client) -> InterfaceObservation:
        self.monkeypatch.setattr(module.pdf_to_scouts, "main", _fake_pdf_main_success(_SCOUTS_CSV_BODY))
        before = _tasks_snapshot()
        resp = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        task = _only_spawned_task(before)
        await asyncio.wait_for(task, timeout=5)
        await _drain_via_route(module, operation_id)
        return InterfaceObservation(
            status=resp.status_code,
            body={
                "scouts_csv_written": module.SCOUTS_CSV.exists(),
                "busy_after": module.busy["pdf-extract"],
            },
        )

    async def _route_UI_ROUTE_025(self, module, client) -> InterfaceObservation:
        self.monkeypatch.setattr(module.pdf_to_scouts, "main", _fake_pdf_main_error("boom-pdf"))
        before = _tasks_snapshot()
        resp = await client.post(
            "/api/pdf-extract", files={"files": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        )
        assert resp.status_code == 202
        operation_id = resp.json()["operation_id"]
        task = _only_spawned_task(before)
        await asyncio.wait_for(task, timeout=5)
        _, events = await _drain_via_route(module, operation_id)
        error_events = [event for event in events if event.get("type") == "error"]
        return InterfaceObservation(
            status=resp.status_code,
            body={
                "error_message": error_events[0]["message"] if error_events else None,
                "busy_after": module.busy["pdf-extract"],
            },
        )

    async def _route_UI_ROUTE_026(self, module, client) -> InterfaceObservation:
        frame_case = next(case for case in SSE_FRAME_CASES if case.meta.case_id == "SSE-FRAME-002")
        operation_id, task = await _start_schedule_operation(module, client, self.monkeypatch, frame_case)
        await asyncio.wait_for(task, timeout=5)
        _, events = await _drain_via_route(module, operation_id)
        batch_done = next(event for event in events if event["type"] == "batch_done")
        return InterfaceObservation(
            status=202,
            body={
                "scouts_processed": batch_done["scouts_processed"],
                "busy_after": module.busy["schedule-download"],
                "current_download_after": dict(module.current_download),
            },
        )

    async def _route_UI_ROUTE_027(self, module, client) -> InterfaceObservation:
        frame_case = next(
            case for case in SSE_FRAME_CASES if case.meta.case_id == "SSE-FRAME-005"
        )
        operation_id, task = await _start_schedule_operation(module, client, self.monkeypatch, frame_case)
        await asyncio.wait_for(task, timeout=5)
        _, events = await _drain_via_route(module, operation_id)
        error_events = [event for event in events if event["type"] == "error"]
        return InterfaceObservation(
            status=202,
            body={
                "error_message": error_events[0]["message"] if error_events else None,
                "busy_after": module.busy["schedule-download"],
                "current_download_after": dict(module.current_download),
            },
        )

    async def _route_UI_ROUTE_028(self, module, client) -> InterfaceObservation:
        frame_case = next(case for case in SSE_FRAME_CASES if case.meta.case_id == "SSE-FRAME-002")
        operation_id, task = await _start_schedule_operation(module, client, self.monkeypatch, frame_case)
        await asyncio.wait_for(task, timeout=5)
        resp, _events = await _drain_via_route(module, operation_id)
        return InterfaceObservation(
            status=resp.status_code,
            body={
                "media_type": resp.media_type,
                "operation_removed": operation_id not in module.operations,
            },
        )

    async def _route_UI_ROUTE_029(self, module, client) -> InterfaceObservation:
        frame_case = next(case for case in SSE_FRAME_CASES if case.meta.case_id == "SSE-FRAME-004")
        operation_id, task = await _start_schedule_operation(module, client, self.monkeypatch, frame_case)
        resp = await module.operation_events(operation_id)
        gen = resp.body_iterator
        await gen.__anext__()  # consume exactly one real frame
        await gen.aclose()  # simulate the client disconnecting mid-stream
        removed_immediately = operation_id not in module.operations
        await asyncio.wait_for(task, timeout=5)  # the detached worker still finishes on its own
        return InterfaceObservation(
            status=200, body={"operation_removed_after_close": removed_immediately}
        )

    async def _route_UI_ROUTE_030(self, module, client) -> InterfaceObservation:
        opened: list[str] = []

        def _record_open(url: str) -> bool:
            opened.append(url)
            return True

        module.webbrowser.open = _record_open
        self._write_summary(
            module, "2026-07-23_1200", {"html_report": "../../elsewhere/evil.html"}
        )
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
        assert opened, "webbrowser.open was never called"
        return InterfaceObservation(
            status=resp.status_code,
            body={"url_contains_unsanitized_value": "../../elsewhere/evil.html" in opened[0]},
        )

    # -- sse-frame / sse-clean (bespoke per case_id, over the SseCase catalog) ------------------

    async def _ctx_sse_frame(self, case: SseCase, root: Path) -> object:
        async with load_legacy_ui(root / "data") as module, _client(module) as client:
            operation_id, task = await _start_schedule_operation(module, client, self.monkeypatch, case)
            await asyncio.wait_for(task, timeout=5)
            _, events = await _drain_via_route(module, operation_id)
            return SseFrameObservation(
                frame_types=tuple(event["type"] for event in events),
                frames=tuple(events),
            )

    async def _ctx_sse_clean(self, case: SseCase, root: Path) -> object:
        member = case.meta.member
        source_case_id = {
            "success": "SSE-FRAME-002",
            "worker-exception": "SSE-FRAME-005",
            "terminal-attendee-failure": "SSE-FRAME-006",
            "client-disconnect": "SSE-FRAME-004",
        }[member]
        frame_case = next(c for c in SSE_FRAME_CASES if c.meta.case_id == source_case_id)
        async with load_legacy_ui(root / "data") as module, _client(module) as client:
            operation_id, task = await _start_schedule_operation(
                module, client, self.monkeypatch, frame_case
            )
            if member == "client-disconnect":
                resp = await module.operation_events(operation_id)
                gen = resp.body_iterator
                await gen.__anext__()
                await gen.aclose()
                operation_removed = operation_id not in module.operations
                await asyncio.wait_for(task, timeout=5)
            else:
                await asyncio.wait_for(task, timeout=5)
                await _drain_via_route(module, operation_id)
                operation_removed = operation_id not in module.operations
            return SseCleanObservation(
                operation_removed=operation_removed,
                busy_reset=module.busy["schedule-download"] is False,
                current_download_cleared=module.current_download == {},
                task_done=task.done(),
            )


@pytest.mark.parametrize(("case", "context_id"), execution_params(INTERFACE_CASES))
async def test_interface_execution(
    case: InterfaceCase, context_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = await LegacyInterfaceRunner(context_id, monkeypatch).run(case, root=tmp_path)
    expected = case.expected_by_context[context_id]
    if isinstance(expected, InterfaceObservation) and expected.body is None:
        assert isinstance(observed, InterfaceObservation)
        assert observed.status == expected.status
        assert observed.headers == expected.headers
    else:
        assert observed == expected


@pytest.mark.parametrize(
    ("case", "context_id"), execution_params(SSE_FRAME_CASES + SSE_CLEAN_CASES)
)
async def test_sse_execution(
    case: SseCase, context_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = await LegacyInterfaceRunner(context_id, monkeypatch).run(case, root=tmp_path)
    expected = case.expected_by_context[context_id]
    assert observed == expected


def test_interface_registry_is_structurally_valid() -> None:
    # CLI-SCHED is also an INTERFACE-domain axis (Task 21 continuation), but its cases live in
    # tests/matrix/cases/cli_cases.py, not this module's interface_cases.py -- pull them in too
    # so this domain-scoped registry check sees every case an INTERFACE-domain axis here claims.
    # CLI-B-MAIN also cross-references PDF-B-MAIN (a PDF-domain boundary, per axes.py's
    # docstring), so the PDF cases it requires must be included as well.
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.cli_cases import ALL_CLI_METADATA
    from tests.matrix.cases.interface_cases import ALL_INTERFACE_METADATA
    from tests.matrix.cases.pdf_cases import PDF_CASES
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    pdf_metadata = tuple(case.meta for case in PDF_CASES)
    ui_axes = [
        axis for axis in AXES if axis.domain is Domain.INTERFACE or axis.domain is Domain.PDF
    ]
    ui_boundaries = [
        b for b in BOUNDARIES if b.domain is Domain.INTERFACE or b.domain is Domain.PDF
    ]

    errors = validate_registry(
        ALL_INTERFACE_METADATA + ALL_CLI_METADATA + pdf_metadata,
        ui_axes,
        ui_boundaries,
        [],
        list(POLICIES),
    )
    assert errors == ()
