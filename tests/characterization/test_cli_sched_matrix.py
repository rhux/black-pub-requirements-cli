"""Typed matrix execution of scout_schedule_cli.py's CLI-entry catalog (Task 21 continuation).

Drives the REAL ``scout_schedule_cli.main()`` (a pure re-export of
``scoutmb.interfaces.cli.schedule.main``, B10.2) / ``parse_args()``. B10.2 moved all acquisition
orchestration into the package: ``async_main`` no longer opens its own browser or drives
``navigate_and_trigger_schedule``/``discover_name``/``post_requirement`` directly, and ``main()``
no longer calls ``async_main`` at all -- it calls ``scoutmb.interfaces.cli.schedule.run()``
directly. The three members that must reach real acquisition logic (empty-success,
one-scout-success, partial-failure) now monkeypatch
``scoutmb.interfaces.cli.composition.build_launched_browser`` -- the function's SOURCE module,
looked up fresh by ``run()``'s own function-local import every call -- to yield a Task-19
``StrictFakeBrowser`` scripted exactly like ``test_acquisition_matrix.py``'s ``ACQ-SCHED-*``
cases (the same real gateway/service drives both, proven parity-equivalent by
``tests/parity/test_acquisition_parity.py``). The two exception-wrapper members
(top-level-exception, keyboard-interrupt) monkeypatch ``scoutmb.interfaces.cli.schedule.run``
itself -- the function ``main()`` actually calls -- so nothing below it ever runs.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import scout_schedule_cli as cli
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import (
    _class_row,
    _req,
    _req_row,
    _requirement_payload,
    _sched,
    _schedule_payload,
)
from tests.matrix.cases.cli_cases import CLI_CASES, CliCase, CliObservation
from tests.matrix.pytest_support import execution_params

_CSV_HEADER = "Attendee Name,Registrant Type,QR Code Contents\r\n"
_ATTENDEE_A = "90000001"
_ATTENDEE_B = "90000002"
_CLASS_A = "2000001"
_CLASS_B = "2000002"


def _patch_launched_browser(monkeypatch: pytest.MonkeyPatch, browser: StrictFakeBrowser) -> None:
    """Patches build_launched_browser at its SOURCE module (composition.py) -- run()'s own
    function-local `from scoutmb.interfaces.cli.composition import (..., build_launched_browser,
    ...)` looks this attribute up fresh every call, so patching it here, before invoking main(),
    is picked up correctly. Patching `scoutmb.interfaces.cli.schedule.build_launched_browser`
    would NOT work: that name is never bound at schedule.py's module level, only as a local
    inside run()'s own function scope after it has already been called."""

    @asynccontextmanager
    async def fake_launched_browser(*, headed: bool, channel: str | None):
        yield browser

    monkeypatch.setattr(
        "scoutmb.interfaces.cli.composition.build_launched_browser", fake_launched_browser
    )


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> tuple[int, str]:
    """Runs the real ``cli.main()`` with a monkeypatched ``sys.argv`` and captures stderr."""
    monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", *argv])
    import contextlib
    import io

    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = cli.main()
    return code, stderr.getvalue()


def _write_csv(path: Path, rows: list[tuple[str, str, str]]) -> None:
    body = _CSV_HEADER + "".join(f"{name},{rtype},{url}\r\n" for name, rtype, url in rows)
    path.write_text(body, encoding="utf-8-sig")


class CliRunner:
    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: CliCase, *, root: Path, monkeypatch: pytest.MonkeyPatch) -> object:
        handler = getattr(self, f"_ctx_{case.meta.case_id.replace('-', '_')}")
        return handler(case, root, monkeypatch)

    # -- CLI-SCHED-001: defaults/help --------------------------------------------------------

    def _ctx_CLI_SCHED_001(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        if self.context_id == "help":
            monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", "--help"])
            with pytest.raises(SystemExit) as exc_info:
                cli.main()
            return {"exit_code": exc_info.value.code}
        input_csv = root / "scouts.csv"
        _write_csv(input_csv, [])
        monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", "--input", str(input_csv)])
        args = cli.parse_args()
        return {
            "sheet": args.sheet,
            "output_name": args.output.name,
            "timeout": args.timeout,
            "request_delay_ms": args.request_delay_ms,
            "scout_delay_ms": args.scout_delay_ms,
            "allow_dead_assets": args.allow_dead_assets,
            "include_adults": args.include_adults,
            "no_html": args.no_html,
            "html_name": args.html_name,
            "email_report": args.email_report,
        }

    # -- CLI-SCHED-002: empty success ---------------------------------------------------------

    def _ctx_CLI_SCHED_002(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        # Deliberately NOT patching async_playwright: load_inputs raises before it is ever
        # reached for a zero-filtered scout list (see the case rationale).
        input_csv = root / "scouts.csv"
        _write_csv(input_csv, [])
        output_dir = root / "out"
        code, stderr = _run_main(
            monkeypatch,
            ["--input", str(input_csv), "--output", str(output_dir), "--no-html"],
        )
        return CliObservation(return_code=code)

    # -- CLI-SCHED-003: one-scout success -----------------------------------------------------

    def _ctx_CLI_SCHED_003(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        script = StrictScript(
            (
                _sched(_ATTENDEE_A, _schedule_payload((_class_row(_CLASS_A),))),
                _req(_ATTENDEE_A, _CLASS_A, _requirement_payload((_req_row(),))),
            )
        )
        browser = StrictFakeBrowser(script, FakeClock())
        _patch_launched_browser(monkeypatch, browser)
        input_csv = root / "scouts.csv"
        _write_csv(
            input_csv,
            [("Avery Archer", "Youth", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0001")],
        )
        output_dir = root / "out"
        code, stderr = _run_main(
            monkeypatch,
            [
                "--input",
                str(input_csv),
                "--output",
                str(output_dir),
                "--no-html",
                "--request-delay-ms",
                "0",
            ],
        )
        return CliObservation(return_code=code)

    # -- CLI-SCHED-004: partial failure -------------------------------------------------------

    def _ctx_CLI_SCHED_004(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        # Avery's schedule+requirement round trip succeeds; Bo's schedule payload carries a
        # failure status (status.status != 1) -- the real gateway turns that into a per-scout
        # error the same way ACQ-SCHED-004 already characterizes, never a raised exception that
        # would stop the batch.
        script = StrictScript(
            (
                _sched(_ATTENDEE_A, _schedule_payload((_class_row(_CLASS_A),))),
                _req(_ATTENDEE_A, _CLASS_A, _requirement_payload((_req_row(),))),
                _sched(_ATTENDEE_B, _schedule_payload((_class_row(_CLASS_B),), status=0)),
            )
        )
        browser = StrictFakeBrowser(script, FakeClock())
        _patch_launched_browser(monkeypatch, browser)
        input_csv = root / "scouts.csv"
        _write_csv(
            input_csv,
            [
                ("Avery Archer", "Youth", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0001"),
                ("Bo Baker", "Youth", "https://scoutingevent.com/mobile/bad?t=TESTTOKEN0002"),
            ],
        )
        output_dir = root / "out"
        code, stderr = _run_main(
            monkeypatch,
            [
                "--input",
                str(input_csv),
                "--output",
                str(output_dir),
                "--no-html",
                "--scout-delay-ms",
                "0",
                "--request-delay-ms",
                "0",
            ],
        )
        return CliObservation(return_code=code)

    # -- CLI-SCHED-005/006: main()'s own exception wrapper ------------------------------------

    def _ctx_CLI_SCHED_005(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        async def boom(config: object, **kwargs: object) -> int:
            raise RuntimeError("boom")

        monkeypatch.setattr("scoutmb.interfaces.cli.schedule.run", boom)
        input_csv = root / "scouts.csv"
        _write_csv(input_csv, [])
        code, stderr = _run_main(monkeypatch, ["--input", str(input_csv)])
        found = ("ERROR: boom",) if "ERROR: boom" in stderr else ()
        return CliObservation(return_code=code, stderr_contains=found)

    def _ctx_CLI_SCHED_006(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        async def interrupt(config: object, **kwargs: object) -> int:
            raise KeyboardInterrupt()

        monkeypatch.setattr("scoutmb.interfaces.cli.schedule.run", interrupt)
        input_csv = root / "scouts.csv"
        _write_csv(input_csv, [])
        code, stderr = _run_main(monkeypatch, ["--input", str(input_csv)])
        found = ("Interrupted.",) if "Interrupted." in stderr else ()
        return CliObservation(return_code=code, stderr_contains=found)


@pytest.mark.parametrize(("case", "context_id"), execution_params(CLI_CASES))
def test_cli_sched_execution(
    case: CliCase, context_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = CliRunner(context_id).run(case, root=tmp_path, monkeypatch=monkeypatch)
    expected = case.expected_by_context[context_id]
    if isinstance(expected, CliObservation):
        assert isinstance(observed, CliObservation)
        assert observed.return_code == expected.return_code
        if expected.stderr_contains:
            assert observed.stderr_contains == expected.stderr_contains
    else:
        assert observed == expected


def test_cli_sched_registry_is_structurally_valid() -> None:
    # Validates the CLI-SCHED axis together with BOTH boundaries it references: CLI-B-MAIN
    # (its own scout_schedule_cli.main cases) and PDF-B-MAIN, the cross-referenced
    # pdf_to_scouts.main boundary from Task 18. PDF-B-MAIN's required_case_ids are PDF-domain
    # cases already fully declared in tests/matrix/cases/pdf_cases.py -- pulling in
    # ALL_PDF_METADATA here (rather than duplicating those cases) is what proves the
    # cross-reference is real and not a dangling/duplicated expectation.
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.cli_cases import ALL_CLI_METADATA
    from tests.matrix.cases.pdf_cases import PDF_CASES
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    pdf_metadata = tuple(case.meta for case in PDF_CASES)
    relevant_axes = [
        axis for axis in AXES if axis.axis_id == "CLI-SCHED" or axis.domain is Domain.PDF
    ]
    cli_boundaries = [
        b for b in BOUNDARIES if b.boundary_id == "CLI-B-MAIN" or b.domain is Domain.PDF
    ]

    errors = validate_registry(
        ALL_CLI_METADATA + pdf_metadata, relevant_axes, cli_boundaries, [], list(POLICIES)
    )
    assert errors == ()
