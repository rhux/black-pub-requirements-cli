"""Typed matrix execution of the interface characterization catalog (Task 21).

Every executable ``UI-*`` / ``RUN-*`` case declares one execution context; ``execution_params``
expands them. Every context here drives the REAL ``ui.server`` FastAPI app (never mocked),
reached through ``httpx.AsyncClient`` bound with ``ASGITransport`` -- an in-process ASGI call,
never a real socket -- via the isolated ``tests.harnesses.legacy.load_legacy_ui`` reload
harness so each case gets its own ``tmp_path``-scoped data root.

No test writes outside ``tmp_path`` and this module performs no real file or network I/O.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest
from tests.harnesses.legacy import load_legacy_ui
from tests.matrix.cases.interface_cases import (
    INTERFACE_CASES,
    InterfaceCase,
    InterfaceObservation,
)
from tests.matrix.pytest_support import execution_params


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

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

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


@pytest.mark.parametrize(("case", "context_id"), execution_params(INTERFACE_CASES))
async def test_interface_execution(case: InterfaceCase, context_id: str, tmp_path: Path) -> None:
    observed = await LegacyInterfaceRunner(context_id).run(case, root=tmp_path)
    expected = case.expected_by_context[context_id]
    if isinstance(expected, InterfaceObservation) and expected.body is None:
        assert isinstance(observed, InterfaceObservation)
        assert observed.status == expected.status
        assert observed.headers == expected.headers
    else:
        assert observed == expected


def test_interface_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.interface_cases import ALL_INTERFACE_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    ui_axes = [axis for axis in AXES if axis.domain is Domain.INTERFACE]
    ui_boundaries = [b for b in BOUNDARIES if b.domain is Domain.INTERFACE]

    errors = validate_registry(
        ALL_INTERFACE_METADATA, ui_axes, ui_boundaries, [], list(POLICIES)
    )
    assert errors == ()
