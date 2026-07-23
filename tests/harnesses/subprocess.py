"""Capture a legacy CLI's exit code and streams as an in-memory observation.

Used by CLI-surface characterization (e.g. the corpus verifier's stdout/stderr contract).
Runs the tool in-process by calling its ``main(argv)`` under captured streams — no real
subprocess, so the offline socket policy and the pytest data sandbox both stay in force.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    def stdout_lines(self) -> list[str]:
        return self.stdout.splitlines()

    def stderr_lines(self) -> list[str]:
        return self.stderr.splitlines()


def run_main(main: Callable[[Sequence[str]], int], argv: Sequence[str]) -> CommandResult:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:  # argparse errors raise SystemExit(2)
            # POSIX/Python convention (matches sys.exit()): None means success (0), an int is
            # the code itself, and a non-int (e.g. sys.exit("message")) means failure (1).
            if exc.code is None:
                code = 0
            elif isinstance(exc.code, int):
                code = exc.code
            else:
                code = 1
    return CommandResult(code, out.getvalue(), err.getvalue())
