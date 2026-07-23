"""Capture a legacy CLI's exit code and streams as an in-memory observation.

Used by CLI-surface characterization (e.g. the corpus verifier's stdout/stderr contract).
Runs the tool in-process by calling its ``main(argv)`` under captured streams — no real
subprocess, so the offline socket policy and the pytest data sandbox both stay in force.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Heavy optional dependencies whose presence in a fresh interpreter we care about when the
# legacy module is imported under a constrained dependency profile.
_TRACKED_IMPORT_ROOTS = ("playwright", "fitz", "cv2", "openpyxl")

# Runs in a clean ``python -I`` child. Installs a meta-path finder that raises ImportError for
# the blocked top-level names, then executes the legacy module straight from its file (no
# sys.path mutation) and reports which tracked roots ended up imported. argv carries the
# profile name, the module file path, the tracked root names (JSON), then the blocked
# top-level names.
_IMPORT_PROBE_SOURCE = """
import importlib.util
import json
import sys

profile = sys.argv[1]
module_path = sys.argv[2]
tracked = set(json.loads(sys.argv[3]))
blocked = set(sys.argv[4:])


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in blocked:
            raise ImportError("blocked by import probe: " + name)
        return None


sys.meta_path.insert(0, _Blocker())
exception_type = None
try:
    spec = importlib.util.spec_from_file_location("scout_schedule_cli", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scout_schedule_cli"] = module
    spec.loader.exec_module(module)
    getattr(module, "load_inputs")
except Exception as exc:
    exception_type = type(exc).__name__
imported = sorted({n.split(".")[0] for n in sys.modules if n.split(".")[0] in tracked})
sys.stdout.write(json.dumps({
    "profile": profile,
    "exception_type": exception_type,
    "imported_modules": imported,
}))
"""


@dataclass(frozen=True, slots=True)
class ImportProbeResult:
    profile: str
    returncode: int
    exception_type: str | None
    imported_modules: tuple[str, ...]


def run_import_probe(
    profile: str, module_path: Path, blocked: Iterable[str]
) -> ImportProbeResult:
    """Import the legacy module in an isolated child with ``blocked`` roots unavailable.

    Uses ``sys.executable -I`` (ignores user site-packages and environment) so the child's
    dependency picture is decided solely by the meta-path blocker, not the parent process.
    """
    # Fixed executable, no shell, fully controlled argv -- the child cannot run arbitrary code.
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _IMPORT_PROBE_SOURCE,
            profile,
            str(module_path),
            json.dumps(list(_TRACKED_IMPORT_ROOTS)),
            *blocked,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if not completed.stdout.strip():
        raise RuntimeError(
            "import probe produced no stdout "
            f"(returncode={completed.returncode!r}, stderr={completed.stderr!r})"
        )
    payload = json.loads(completed.stdout)
    return ImportProbeResult(
        profile=str(payload["profile"]),
        returncode=completed.returncode,
        exception_type=payload["exception_type"],
        imported_modules=tuple(payload["imported_modules"]),
    )


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
