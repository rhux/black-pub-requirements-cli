"""D13/D24: the console scripts genuinely work when installed, run as subprocesses (per the
Phase B spec: calling main() in-process skips the argv[0] the parser actually sees and the
pyproject.toml-generated wrapper), from a directory outside the repository so no relative-path/
CWD coincidence masks a real difference.

Slice 2b B10.4: retired pdf_to_scouts.py (Step 7) and is retiring scout_schedule_cli.py (Step 8,
in a later commit), so this file's original "must match their flat-script predecessors argument
for argument" comparisons (test_schedule_help_matches_flat_script,
test_schedule_missing_required_input_matches_exit_code_and_stderr,
test_schedule_handled_exception_matches_exit_code_and_stderr_prefix,
test_pdf_help_matches_flat_script) no longer have anything to compare against once their target
flat module is gone -- deleted here, not migrated, as each one's target module retires.
test_keyboard_interrupt_maps_to_130's scout_schedule_cli parametrize case is trimmed in the same
commit that deletes scout_schedule_cli.py itself; its package-module case stays regardless.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_desktop_entrypoint_is_installed() -> None:
    result = subprocess.run(["troop349", "--help"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "--browser" in result.stdout


@pytest.mark.matrix_case(case_id="CLI-SCHED-006", context_id="run", lane="default")
def test_keyboard_interrupt_maps_to_130(monkeypatch: pytest.MonkeyPatch) -> None:
    """KeyboardInterrupt -> 130 is a UNIT test against main() in-process, not a subprocess:
    reliably delivering a real SIGINT to a subprocess mid-run requires it to be blocked on
    something (a live Playwright launch), which is out of scope for an entrypoint-parity check.
    This proves the exception-to-exit-code MAPPING itself.

    Previously parametrized over scout_schedule_cli too (retired in Slice 2b B10.4) -- that
    module's main was already a pure re-export of scoutmb.interfaces.cli.schedule.main (the
    literal same function object, B10.2), so the two parametrize cases were never actually
    exercising independent code paths."""
    import importlib

    module = importlib.import_module("scoutmb.interfaces.cli.schedule")
    monkeypatch.setattr(sys, "argv", ["troop349-schedule", "--input", "unused.csv"])

    def _raise_keyboard_interrupt(coro: object) -> int:
        coro.close()  # avoid a "coroutine was never awaited" warning
        raise KeyboardInterrupt

    monkeypatch.setattr(module.asyncio, "run", _raise_keyboard_interrupt)
    assert module.main() == 130
