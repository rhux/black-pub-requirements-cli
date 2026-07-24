"""Typed matrix execution of scout_schedule_cli.py's CLI-entry catalog (Task 21 continuation).

Drives the REAL ``scout_schedule_cli.main()`` / ``parse_args()``. The three members that must
reach ``async_main``'s body (empty-success, one-scout-success, partial-failure) narrowly
monkeypatch ``cli.async_playwright`` to a fake context manager yielding a Task-19
``StrictFakeBrowser`` -- never a real Chromium process -- plus the same
``navigate_and_trigger_schedule``/``discover_name``/``post_requirement`` monkeypatches
``test_process_scout.py`` already established. The two exception-wrapper members
(top-level-exception, keyboard-interrupt) monkeypatch ``cli.async_main`` itself, so nothing
below it ever runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import scout_schedule_cli as cli
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.cli_cases import CLI_CASES, CliCase, CliObservation
from tests.matrix.pytest_support import execution_params

_CSV_HEADER = "Attendee Name,Registrant Type,QR Code Contents\r\n"


class _FakePlaywrightCM:
    """Stands in for ``async_playwright()``'s real context manager (Task 21 continuation).

    Implements only ``__aenter__``/``__aexit__`` and the single ``chromium.launch(...)`` call
    ``async_main`` makes on the object it yields -- never a real Chromium subprocess.
    """

    def __init__(self, browser: StrictFakeBrowser) -> None:
        self._browser = browser

    async def __aenter__(self) -> SimpleNamespace:
        async def _launch(**kwargs: object) -> StrictFakeBrowser:
            return self._browser

        return SimpleNamespace(chromium=SimpleNamespace(launch=_launch))

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _patch_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = StrictFakeBrowser(StrictScript(()), FakeClock())
    monkeypatch.setattr(cli, "async_playwright", lambda: _FakePlaywrightCM(browser))


async def _ok_nav(page: object, url: str, timeout: int) -> object:
    from tests.factories.payloads import schedule_payload

    class _Req:
        def __init__(self, post_data: str) -> None:
            self.post_data = post_data

    class _Resp:
        def __init__(self, payload: object, post_data: str) -> None:
            self._payload = payload
            self.request = _Req(post_data)

        async def json(self) -> object:
            return self._payload

    return _Resp(schedule_payload(), "attendeeID=90000001")


async def _ok_name(page: object, fallback: str) -> str:
    return fallback


async def _ok_post(page: object, attendee_id: str, class_id: str) -> object:
    from tests.factories.payloads import requirement_payload

    return requirement_payload()


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
        monkeypatch.setattr(cli, "navigate_and_trigger_schedule", _ok_nav)
        monkeypatch.setattr(cli, "discover_name", _ok_name)
        monkeypatch.setattr(cli, "post_requirement", _ok_post)
        _patch_playwright(monkeypatch)
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
        async def flaky_nav(page: object, url: str, timeout: int) -> object:
            if "bad" in url:
                raise RuntimeError("schedule exploded")
            return await _ok_nav(page, url, timeout)

        monkeypatch.setattr(cli, "navigate_and_trigger_schedule", flaky_nav)
        monkeypatch.setattr(cli, "discover_name", _ok_name)
        monkeypatch.setattr(cli, "post_requirement", _ok_post)
        _patch_playwright(monkeypatch)
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
        async def boom(args: object, **kwargs: object) -> int:
            raise RuntimeError("boom")

        monkeypatch.setattr(cli, "async_main", boom)
        input_csv = root / "scouts.csv"
        _write_csv(input_csv, [])
        code, stderr = _run_main(monkeypatch, ["--input", str(input_csv)])
        found = ("ERROR: boom",) if "ERROR: boom" in stderr else ()
        return CliObservation(return_code=code, stderr_contains=found)

    def _ctx_CLI_SCHED_006(
        self, case: CliCase, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> object:
        async def interrupt(args: object, **kwargs: object) -> int:
            raise KeyboardInterrupt()

        monkeypatch.setattr(cli, "async_main", interrupt)
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
