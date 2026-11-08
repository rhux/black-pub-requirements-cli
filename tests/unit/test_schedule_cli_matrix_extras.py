"""Package-side matrix runner for the CLI-SCHED-* cases tests/matrix/cases/cli_cases.py declares
that had no marked, passing test anywhere in the tree (Gate 2 test-coverage close-out).

CLI-SCHED-001's "defaults" context and CLI-SCHED-006 ("keyboard-interrupt") already had a
genuinely-covering test elsewhere (tests/contracts/test_cli_defaults_parity.py,
tests/parity/test_entrypoint_parity.py) -- the marker was added directly there instead of being
duplicated here. CLI-SCHED-003 ("one-scout-success") and CLI-SCHED-004 ("partial-failure") mirror
the same real fake-browser wiring tests/vertical/test_legacy_flows.py already proves end to end
(Task 19's StrictFakeBrowser/StrictScript/FakeClock), but as independent, narrowly-scoped tests
here: that file's own covering assertions live inside FLOW-SUCCESS-001/FLOW-PARTIAL-001, which
already carry THEIR OWN matrix_case marker, and pytest_plugins/matrix_gate.py's
``item.get_closest_marker("matrix_case")`` only ever reads one marker per test item.
"""

from __future__ import annotations

import csv
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

from scoutmb.interfaces.cli import schedule as schedule_cli


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


def _write_scouts_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["Attendee Name", "Registrant Type", "QR Code Contents"]
        )
        writer.writeheader()
        for name, url in rows:
            writer.writerow(
                {"Attendee Name": name, "Registrant Type": "Youth", "QR Code Contents": url}
            )


def _run_with_fake_browser(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], browser: StrictFakeBrowser
) -> int:
    @asynccontextmanager
    async def fake_launched_browser(*, headed: bool, channel: str | None):
        try:
            yield browser
        finally:
            await browser.close()

    monkeypatch.setattr(
        "scoutmb.interfaces.cli.composition.build_launched_browser", fake_launched_browser
    )
    monkeypatch.setattr(sys, "argv", ["troop349-schedule", *argv])
    return schedule_cli.main()


# ---------------------------------------------------------------------------------------------
# CLI-SCHED-001 -- help context (defaults context is covered by
# tests/contracts/test_cli_defaults_parity.py, marked there directly).
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="CLI-SCHED-001", context_id="help", lane="default")
def test_cli_sched_001_help_exits_zero_with_usage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["troop349-schedule", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        schedule_cli.main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip().lower().startswith("usage")


# ---------------------------------------------------------------------------------------------
# CLI-SCHED-002 -- an all-header (zero-scout) input fails closed via main()'s except Exception,
# exit code 2, before async_playwright/build_launched_browser is ever reached.
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="CLI-SCHED-002", context_id="run", lane="default")
def test_cli_sched_002_empty_scout_list_fails_closed_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = tmp_path / "scouts.csv"
    csv_path.write_text("Attendee Name,Registrant Type,QR Code Contents\n", encoding="utf-8")

    # If build_launched_browser were ever reached, this would raise -- proving the browser
    # genuinely never launches for this member.
    def _must_not_launch(**kwargs: object) -> None:
        raise AssertionError("build_launched_browser must not be reached for an empty scout list")

    monkeypatch.setattr(
        "scoutmb.interfaces.cli.composition.build_launched_browser", _must_not_launch
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["troop349-schedule", "--input", str(csv_path), "--output", str(tmp_path / "out")],
    )

    exit_code = schedule_cli.main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "No ScoutingEvent QR URLs found" in captured.err


# ---------------------------------------------------------------------------------------------
# CLI-SCHED-003 -- a single scout whose schedule/requirement fetches both succeed.
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="CLI-SCHED-003", context_id="run", lane="default")
def test_cli_sched_003_one_scout_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The real gateway's egress check runs before every navigation, even against a fake page --
    # opt in the same way tests/vertical/conftest.py does for its synthetic scoutingevent.com URLs.
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    csv_path = tmp_path / "scouts.csv"
    _write_scouts_csv(
        csv_path, [("Avery Archer", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0001")]
    )
    output_dir = tmp_path / "out"

    script = StrictScript(
        (
            (
                ExpectedRequest("schedule", "90000001"),
                ScriptedResponse(
                    value={"status": {"status": 1}, "data": [_schedule_row("2000001")]}
                ),
            ),
            (
                ExpectedRequest("requirement", "90000001", "2000001"),
                ScriptedResponse(value={"status": {"status": 1}, "data": [_requirement_row()]}),
            ),
        )
    )
    browser = StrictFakeBrowser(script, FakeClock())

    exit_code = _run_with_fake_browser(
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
    assert exit_code == 0
    assert browser.closed
    assert len(browser.contexts) == 1
    assert browser.contexts[0].closed
    assert (output_dir / "errors.csv").exists()
    with (output_dir / "errors.csv").open(encoding="utf-8-sig", newline="") as stream:
        assert list(csv.DictReader(stream)) == []


# ---------------------------------------------------------------------------------------------
# CLI-SCHED-004 -- two scouts, one's schedule fetch fails terminally; the batch continues and
# main()'s exit code is 1 because any(result.errors ...) is true.
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="CLI-SCHED-004", context_id="run", lane="default")
def test_cli_sched_004_partial_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    csv_path = tmp_path / "scouts.csv"
    _write_scouts_csv(
        csv_path,
        [
            ("Avery Archer", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0001"),
            ("Bo Baker", "https://scoutingevent.com/mobile/x?t=TESTTOKEN0002"),
        ],
    )
    output_dir = tmp_path / "out"

    script = StrictScript(
        (
            (
                ExpectedRequest("schedule", "90000001"),
                ScriptedResponse(
                    value={"status": {"status": 1}, "data": [_schedule_row("2000001")]}
                ),
            ),
            (
                ExpectedRequest("requirement", "90000001", "2000001"),
                ScriptedResponse(value={"status": {"status": 1}, "data": [_requirement_row()]}),
            ),
            (
                ExpectedRequest("schedule", "90000002"),
                ScriptedResponse(value={"status": {"status": 0}, "data": []}),
            ),
        )
    )
    browser = StrictFakeBrowser(script, FakeClock())

    exit_code = _run_with_fake_browser(
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
    assert exit_code == 1
    assert browser.closed
    assert len(browser.contexts) == 2
    assert all(context.closed for context in browser.contexts)

    with (output_dir / "errors.csv").open(encoding="utf-8-sig", newline="") as stream:
        error_rows = list(csv.DictReader(stream))
    assert len(error_rows) == 1


# ---------------------------------------------------------------------------------------------
# CLI-SCHED-005 -- run() itself raising a plain Exception maps to "ERROR: ..." + exit code 2.
# ---------------------------------------------------------------------------------------------


@pytest.mark.matrix_case(case_id="CLI-SCHED-005", context_id="run", lane="default")
def test_cli_sched_005_top_level_exception_maps_to_error_message_and_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def _boom(config: object, **kwargs: object) -> int:
        raise Exception("boom")

    monkeypatch.setattr(schedule_cli, "run", _boom)
    monkeypatch.setattr(sys, "argv", ["troop349-schedule", "--input", str(tmp_path / "scouts.csv")])

    exit_code = schedule_cli.main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "ERROR: boom" in captured.err
