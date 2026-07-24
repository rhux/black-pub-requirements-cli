"""Real end-to-end vertical-flow characterization (Task 22, Slice 1b Phase A).

Covers ``FLOW-SUCCESS-001`` and ``FLOW-PARTIAL-001``: a genuine wire-up of FIVE real production
stages through ONE flow test each --

1. A generated PDF (Task 18's real ``tests.factories.pdf_builder.build_pdf``).
2. The REAL ``pdf_to_scouts.main`` (extraction + attendee CSV writing).
3. The REAL ``scout_schedule_cli.load_inputs``.
4. The REAL ``scout_schedule_cli.main`` -> ``async_main`` -> ``process_scout`` /
   ``navigate_and_trigger_schedule`` / ``post_requirement`` -- driven by Task 19's strict
   fake Browser/Context/Page (``tests/fakes/browser.py``, ``tests/fakes/acquisition.py``,
   ``tests/fakes/clock.py``). Only ``cli.async_playwright`` is monkeypatched, to a fake context
   manager whose ``chromium.launch(...)`` returns a ``StrictFakeBrowser`` -- the acquisition
   functions themselves (``navigate_and_trigger_schedule``, ``discover_name``,
   ``post_requirement``, ``process_scout``) are never monkeypatched here, unlike
   ``tests/matrix/cases/cli_cases.py``'s CLI-SCHED catalog: this file exists specifically to
   prove those real functions work end to end against the strict fakes, one layer above where
   ``tests/characterization/test_acquisition_matrix.py`` already proves it for a single scout.
5. The REAL ``annotate_requirement_statuses``/``write_outputs`` (invoked internally by
   ``async_main``) and the REAL UI read routes (Task 21's ``tests.harnesses.legacy.load_legacy_ui``
   harness) reading the generated output directory.

No test writes outside ``tmp_path`` and no test performs real network I/O.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import scout_schedule_cli as cli
from tests.factories.pdf_builder import build_pdf
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.harnesses.legacy import load_legacy_ui
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse
from tests.matrix.cases.pdf_cases import PdfPageSpec

pytestmark = pytest.mark.vertical

_CSV_HEADER_FIELDS = ("Attendee Name", "Registrant Type", "QR Code Contents")


def _schedule_row(
    class_id: str,
    class_number: str = "26MB1",
    name: str = "Chess",
    *,
    has_req: str = "1",
    completed: str = "0",
) -> dict[str, object]:
    return {
        "classP4ID": class_id,
        "CLASS_NAME": f"MoTuWeTh - {name} - {class_number} (Pavilion)",
        "CLASS_NAME_ONLY": name,
        "CLASS_NBR": class_number,
        "PERIOD_NAME": "A Block",
        "CLASS_STIME": "09:00 AM",
        "STIME": "09:00:00",
        "LOCATION_ROOM_NAME": "Pavilion",
        "HAS_REQ": has_req,
        "CLASS_COMPLETED": completed,
        "SES_LKP_PERIOD_TYPE_ID": "1",
    }


def _requirement_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "MDM_LKP_BADGE_REQ_ID": "r1",
        "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
        "MERIT_BADGE_NAME": "Chess",
        "REQ_NBR": "1",
        "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Discuss the history of chess.",
        "COMPLETED_REQ_FLAG": "0",
        "COMPLETED_CLASS_FLAG": "0",
        "REQ_ON_EVENT": "1",
        "PRESENT_DAYS": "MoTuWeTh",
    }
    row.update(overrides)
    return row


class _FakePlaywrightCM:
    """Stands in for ``async_playwright()``'s real context manager (same shape as
    ``tests/matrix/cases/cli_cases.py``'s ``_FakePlaywrightCM``) -- implements only
    ``__aenter__``/``__aexit__`` and the single ``chromium.launch(...)`` call ``async_main``
    makes on the object it yields. Never a real Chromium subprocess."""

    def __init__(self, browser: StrictFakeBrowser) -> None:
        self._browser = browser

    async def __aenter__(self) -> SimpleNamespace:
        async def _launch(**kwargs: object) -> StrictFakeBrowser:
            return self._browser

        return SimpleNamespace(chromium=SimpleNamespace(launch=_launch))

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _build_pdf(pdf_path: Path, attendees: tuple[tuple[str, str, str], ...]) -> None:
    pages = tuple(
        PdfPageSpec(name, registrant_type, qr_url, "embedded")
        for name, registrant_type, qr_url in attendees
    )
    build_pdf(pdf_path, pages)


def _read_attendee_csv(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], browser: StrictFakeBrowser
) -> tuple[int, str]:
    monkeypatch.setattr(cli, "async_playwright", lambda: _FakePlaywrightCM(browser))
    monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", *argv])
    stderr = io.StringIO()
    import contextlib

    with contextlib.redirect_stderr(stderr):
        code = cli.main()
    return code, stderr.getvalue()


def _client(module: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=module.app, raise_app_exceptions=False)  # type: ignore[attr-defined]
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _list_runs(data_root: Path) -> tuple[int, object]:
    async with load_legacy_ui(data_root) as module, _client(module) as client:
        resp = await client.get("/api/runs")
        return resp.status_code, resp.json()


# ---------------------------------------------------------------------------------------------
# FLOW-SUCCESS-001
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="FLOW-SUCCESS-001", context_id="run", lane="default")
def test_flow_success_001_five_stage_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    assert not data_root.exists()  # precondition: nothing written yet

    # -- Stage 1: real synthetic PDF generation (Task 18).
    pdf_path = tmp_path / "schedule.pdf"
    _build_pdf(
        pdf_path,
        (
            ("Avery Archer", "Youth", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0001"),
            ("Bo Baker", "Youth", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0002"),
        ),
    )
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0

    # -- Stage 2: real pdf_to_scouts.main (extraction + attendee CSV).
    import pdf_to_scouts

    csv_path = tmp_path / "scouts.csv"
    pdf_exit_code = pdf_to_scouts.main([str(pdf_path), "-o", str(csv_path), "--strict"])
    assert pdf_exit_code == 0

    attendee_rows = _read_attendee_csv(csv_path)
    assert tuple(attendee_rows[0].keys())[:3] == _CSV_HEADER_FIELDS
    assert len(attendee_rows) == 2
    assert [row["Attendee Name"] for row in attendee_rows] == ["Avery Archer", "Bo Baker"]

    # -- Stage 3: real scout_schedule_cli.load_inputs (sanity-checked directly before the CLI
    # entry point re-runs it internally as part of async_main).
    scouts = cli.load_inputs(csv_path, "Scouts Only", False)
    assert len(scouts) == 2

    # -- Stage 4: real cli.main() -> async_main -> process_scout, driven by Task 19's strict
    # fakes. Probe: the output directory does not exist before the run.
    output_dir = data_root / "runs" / "run-success-001"
    assert not output_dir.exists()

    attendee_ids = ("90000001", "90000002")
    class_ids = ("2000001", "2000002")
    script_pairs: list[tuple[ExpectedRequest, ScriptedResponse]] = []
    for attendee_id, class_id in zip(attendee_ids, class_ids, strict=True):
        script_pairs.append(
            (
                ExpectedRequest("schedule", attendee_id),
                ScriptedResponse(
                    value={"status": {"status": 1}, "data": [_schedule_row(class_id)]}
                ),
            )
        )
        script_pairs.append(
            (
                ExpectedRequest("requirement", attendee_id, class_id),
                ScriptedResponse(value={"status": {"status": 1}, "data": [_requirement_row()]}),
            )
        )
    script = StrictScript(tuple(script_pairs))
    clock = FakeClock()
    browser = StrictFakeBrowser(script, clock)

    exit_code, stderr = _run_cli(
        monkeypatch,
        [
            "--input",
            str(csv_path),
            "--output",
            str(output_dir),
            "--no-html",
            "--request-delay-ms",
            "0",
            "--scout-delay-ms",
            "0",
        ],
        browser,
    )

    script.assert_consumed()
    assert exit_code == 0, stderr  # truthful return code: no scout had an error
    assert browser.closed  # async_main's own `finally: await browser.close()`
    assert len(browser.contexts) == 2
    assert all(context.closed for context in browser.contexts)  # process_scout's own cleanup

    # -- Stage 5 (writers): real write_outputs' generated artifacts.
    assert (output_dir / "scouts.json").exists()
    assert (output_dir / "classes.csv").exists()
    assert (output_dir / "requirements.csv").exists()
    assert (output_dir / "errors.csv").exists()
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["scouts_processed"] == 2
    assert summary["scouts_with_errors"] == 0
    assert summary["classes"] == 2
    assert summary["requirements"] == 2

    raw_files = sorted(p.name for p in (output_dir / "raw").iterdir())
    assert len(raw_files) == 4  # 2 schedule + 2 requirement raw payloads

    # -- Stage 5 (UI read routes): the real ui.server FastAPI app, via Task 21's harness.
    status, runs = asyncio.run(_list_runs(data_root))
    assert status == 200
    assert len(runs) == 1
    (run,) = runs
    assert run["run_id"] == "run-success-001"
    assert run["scouts_processed"] == 2
    assert run["scouts_with_errors"] == 0
    assert run["classes"] == 2
    assert run["requirements"] == 2
    assert run["report_url"] is None  # --no-html: no report was generated


# ---------------------------------------------------------------------------------------------
# FLOW-PARTIAL-001
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="FLOW-PARTIAL-001", context_id="run", lane="default")
def test_flow_partial_001_one_terminal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    pdf_path = tmp_path / "schedule.pdf"
    _build_pdf(
        pdf_path,
        (
            ("Avery Archer", "Youth", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0001"),
            ("Bo Baker", "Youth", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0002"),
        ),
    )
    assert pdf_path.exists()

    import pdf_to_scouts

    csv_path = tmp_path / "scouts.csv"
    assert pdf_to_scouts.main([str(pdf_path), "-o", str(csv_path), "--strict"]) == 0
    attendee_rows = _read_attendee_csv(csv_path)
    assert len(attendee_rows) == 2

    output_dir = data_root / "runs" / "run-partial-001"
    assert not output_dir.exists()

    attendee_ids = ("90000001", "90000002")
    class_id_a = "2000001"
    # Attendee A succeeds normally; attendee B's schedule request returns a terminal
    # (non-retryable) API failure status -- process_scout records this as a bounded per-scout
    # error and moves on (see ACQ-SCHED-004), it never raises out of the batch loop.
    script_pairs: list[tuple[ExpectedRequest, ScriptedResponse]] = [
        (
            ExpectedRequest("schedule", attendee_ids[0]),
            ScriptedResponse(value={"status": {"status": 1}, "data": [_schedule_row(class_id_a)]}),
        ),
        (
            ExpectedRequest("requirement", attendee_ids[0], class_id_a),
            ScriptedResponse(value={"status": {"status": 1}, "data": [_requirement_row()]}),
        ),
        (
            ExpectedRequest("schedule", attendee_ids[1]),
            ScriptedResponse(value={"status": {"status": 0}, "data": []}),
        ),
    ]
    script = StrictScript(tuple(script_pairs))
    clock = FakeClock()
    browser = StrictFakeBrowser(script, clock)

    exit_code, stderr = _run_cli(
        monkeypatch,
        [
            "--input",
            str(csv_path),
            "--output",
            str(output_dir),
            "--no-html",
            "--request-delay-ms",
            "0",
            "--scout-delay-ms",
            "0",
        ],
        browser,
    )

    script.assert_consumed()  # the failing scout never reaches the "requirement" step at all
    assert exit_code == 1  # any(result.errors ...) is true -- truthful partial-failure exit code
    assert browser.closed
    assert len(browser.contexts) == 2
    assert all(context.closed for context in browser.contexts)  # cleanup still ran for both

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["scouts_processed"] == 2
    assert summary["scouts_with_errors"] == 1
    assert summary["classes"] == 1  # only attendee A's class was recorded
    assert summary["requirements"] == 1

    with (output_dir / "errors.csv").open("r", encoding="utf-8-sig", newline="") as stream:
        error_rows = list(csv.DictReader(stream))
    assert len(error_rows) == 1
    assert error_rows[0]["error"] == "Schedule API returned failure: {'status': 0}"

    # Partial artifacts: the failing scout's raw schedule payload IS written (process_scout
    # persists it before checking the status field), but it has no requirement payload.
    raw_files = sorted(p.name for p in (output_dir / "raw").iterdir())
    schedule_files = [name for name in raw_files if name.endswith("-schedule.json")]
    requirement_files = [name for name in raw_files if name.endswith("-requirements.json")]
    assert len(schedule_files) == 2
    assert len(requirement_files) == 1


def test_flow_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.scale_cases import ALL_FLOW_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    flow_axes = [axis for axis in AXES if axis.domain is Domain.FLOW]
    flow_boundaries = [b for b in BOUNDARIES if b.domain is Domain.FLOW]

    errors = validate_registry(ALL_FLOW_METADATA, flow_axes, flow_boundaries, [], list(POLICIES))
    assert errors == ()
