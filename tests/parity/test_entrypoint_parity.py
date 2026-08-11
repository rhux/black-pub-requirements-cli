"""D13/D24: console scripts must match their flat-script predecessors argument for argument,
exit-code for exit-code, byte for byte on stdout/stderr -- except the program name. Run as
INSTALLED SUBPROCESSES (per the Phase B spec: calling main() in-process skips the argv[0] the
parser actually sees and the pyproject.toml-generated wrapper), from a directory outside the
repository so no relative-path/CWD coincidence masks a real difference."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)


def _normalize(text: str, prog: str) -> str:
    """Strips the prog name, then collapses whitespace runs to a single space.

    argparse's HelpFormatter wraps the usage line based on the available width AFTER
    subtracting "usage: " + the prog name's own length -- "scout_schedule_cli.py" (21 chars)
    and "troop349-schedule" (17 chars) wrap their usage line at different column positions even
    though the flag list is byte-for-byte identical, so a straight substring-substitute-then-
    compare (the plan's original approach) fails on wrapping alone, not on any real content
    difference. Collapsing whitespace makes the comparison robust to wrap position while still
    catching a genuinely missing/extra flag or changed help text.
    """
    stripped = re.sub(rf"\b{re.escape(prog)}\b", "PROG", text)
    return re.sub(r"\s+", " ", stripped).strip()


def test_schedule_help_matches_flat_script(tmp_path: Path) -> None:
    flat = _run([sys.executable, str(REPO_ROOT / "scout_schedule_cli.py"), "--help"], cwd=tmp_path)
    packaged = _run(["troop349-schedule", "--help"], cwd=tmp_path)

    assert flat.returncode == packaged.returncode == 0
    assert _normalize(flat.stdout, "scout_schedule_cli.py") == _normalize(
        packaged.stdout, "troop349-schedule"
    )


def test_schedule_missing_required_input_matches_exit_code_and_stderr(tmp_path: Path) -> None:
    flat = _run([sys.executable, str(REPO_ROOT / "scout_schedule_cli.py")], cwd=tmp_path)
    packaged = _run(["troop349-schedule"], cwd=tmp_path)
    assert flat.returncode == packaged.returncode == 2
    assert _normalize(flat.stderr, "scout_schedule_cli.py") == _normalize(
        packaged.stderr, "troop349-schedule"
    )


def test_schedule_handled_exception_matches_exit_code_and_stderr_prefix(tmp_path: Path) -> None:
    """A nonexistent --input FILE (not a missing argument) reaches main()'s own `except
    Exception` branch, not argparse's error path -- a genuinely different code path from the
    test above, and the one main()'s own `print(f"ERROR: {exc}", ...); return 2` handles."""
    missing_file = tmp_path / "does-not-exist.csv"
    flat = _run(
        [sys.executable, str(REPO_ROOT / "scout_schedule_cli.py"), "--input", str(missing_file)],
        cwd=tmp_path,
    )
    packaged = _run(["troop349-schedule", "--input", str(missing_file)], cwd=tmp_path)
    assert flat.returncode == packaged.returncode == 2
    assert flat.stderr.startswith("ERROR: ")
    assert packaged.stderr.startswith("ERROR: ")


def test_pdf_help_matches_flat_script(tmp_path: Path) -> None:
    flat = _run([sys.executable, str(REPO_ROOT / "pdf_to_scouts.py"), "--help"], cwd=tmp_path)
    packaged = _run(["troop349-pdf", "--help"], cwd=tmp_path)
    assert flat.returncode == packaged.returncode == 0
    assert _normalize(flat.stdout, "pdf_to_scouts.py") == _normalize(
        packaged.stdout, "troop349-pdf"
    )


def test_desktop_entrypoint_is_installed() -> None:
    result = subprocess.run(["troop349", "--help"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "--browser" in result.stdout


@pytest.mark.parametrize(
    ("module_name", "argv0"),
    [("scout_schedule_cli", "scout_schedule_cli.py"), ("scoutmb.interfaces.cli.schedule", "troop349-schedule")],
)
def test_keyboard_interrupt_maps_to_130(
    module_name: str, argv0: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt -> 130 is a UNIT test against each main() in-process, not a subprocess:
    reliably delivering a real SIGINT to a subprocess mid-run requires it to be blocked on
    something (a live Playwright launch), which is out of scope for an entrypoint-parity check.
    This proves the exception-to-exit-code MAPPING itself for both modules independently."""
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "argv", [argv0, "--input", "unused.csv"])

    def _raise_keyboard_interrupt(coro: object) -> int:
        coro.close()  # avoid a "coroutine was never awaited" warning
        raise KeyboardInterrupt

    monkeypatch.setattr(module.asyncio, "run", _raise_keyboard_interrupt)
    assert module.main() == 130
