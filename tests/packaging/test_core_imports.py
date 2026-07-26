"""A core-only import must not drag in the heavy optional wheels.

Two tests, because neither alone establishes the contract:
  * blocked-import: proves core NEVER ATTEMPTS the heavy imports (the blocker would raise);
  * capability: proves a genuinely missing stack surfaces as CapabilityUnavailable rather
    than a swallowed ImportError that silently degrades.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
HEAVY = ("cv2", "fitz", "playwright")

# Runs in a clean `python -I` child. sys.path is set INSIDE the source, because -I implies -E
# and would discard a PYTHONPATH we set in the environment.
_PROBE = """
import importlib
import json
import sys

src, blocked, modules = sys.argv[1], set(json.loads(sys.argv[2])), json.loads(sys.argv[3])
sys.path.insert(0, src)


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in blocked:
            raise ImportError("blocked by import probe: " + name)
        return None


sys.meta_path.insert(0, _Blocker())
failed = None
try:
    for name in modules:
        importlib.import_module(name)
except Exception as exc:
    failed = f"{type(exc).__name__}: {exc}"
sys.stdout.write(json.dumps({"failed": failed, "count": len(modules)}))
"""


def _leaf_modules() -> list[str]:
    """Walk the package: a hand-kept list silently stops covering new modules."""
    names: list[str] = []
    for layer in ("core", "ports", "features"):
        root = SRC / "scoutmb" / layer
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(SRC).with_suffix("")
            names.append(".".join(p for p in rel.parts if p != "__init__"))
    return sorted(set(names))


def test_core_layers_never_import_the_heavy_stacks() -> None:
    modules = _leaf_modules()
    assert modules, "package walk found nothing -- the walk is broken, not the package"

    completed = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, str(SRC), json.dumps(HEAVY), json.dumps(modules)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.stdout, f"probe produced no output: {completed.stderr!r}"
    payload = json.loads(completed.stdout)
    assert payload["count"] == len(modules)
    assert payload["failed"] is None, (
        f"a core/ports/features module reached a blocked dependency: {payload['failed']}"
    )


def test_bare_wheel_install_imports_every_core_leaf(tmp_path: Path) -> None:
    """The blocker proves nothing is ATTEMPTED; this proves the shipped wheel is INSTALLABLE
    and importable with no extras at all. Neither implies the other."""
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    wheel = next(dist.glob("*.whl"))
    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", str(venv)], check=True, capture_output=True)
    python = venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
    )

    modules = _leaf_modules()
    code = "".join(f"import {name}\n" for name in modules) + "print('ok')"
    result = subprocess.run([str(python), "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_pdf_capability_fails_closed_through_the_public_entry_point(tmp_path: Path) -> None:
    """Call what a caller calls. Exercising only the private _import_pdf_stack would pass even
    if the public function swallowed the error and returned a degraded result."""
    probe = tmp_path / "page.pdf"
    probe.write_bytes(b"%PDF-1.4\n")

    # Block at the meta-path level so a REAL ImportError is what the guard converts.
    code = f"""
import json, sys
sys.path.insert(0, {str(SRC)!r})


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {{"cv2", "fitz", "numpy"}}:
            raise ImportError("blocked")
        return None


sys.meta_path.insert(0, _Blocker())
from scoutmb.adapters.pdf.extract import decode_embedded_qr
from scoutmb.errors import CapabilityUnavailable
try:
    decode_embedded_qr({str(probe)!r})
    out = {{"raised": None}}
except CapabilityUnavailable as exc:
    out = {{"raised": "CapabilityUnavailable", "message": str(exc)}}
except Exception as exc:
    out = {{"raised": type(exc).__name__, "message": str(exc)}}
sys.stdout.write(json.dumps(out))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    payload = json.loads(completed.stdout)
    assert payload["raised"] == "CapabilityUnavailable", payload
    assert "scoutmb[pdf]" in payload["message"]


def test_decode_embedded_qr_success_path_decodes_the_embedded_image(tmp_path: Path) -> None:
    """The failure-path test above proves CapabilityUnavailable; this proves the happy path
    actually works end-to-end through the guarded public entry point, not just that it fails
    closed when the stack is missing."""
    from scoutmb.adapters.pdf.extract import decode_embedded_qr
    from tests.factories.pdf_builder import build_pdf
    from tests.matrix.cases.pdf_cases import PdfPageSpec

    pdf = build_pdf(
        tmp_path / "page.pdf",
        (
            PdfPageSpec(
                "Avery Example", "Youth", "https://scoutingevent.com/mobile/abc123", "embedded"
            ),
        ),
    )

    assert decode_embedded_qr(pdf) == "https://scoutingevent.com/mobile/abc123"


def test_legacy_pdf_module_attributes_still_resolve() -> None:
    """Frozen tests reach pdf_to_scouts.cv2 and .decode_variants; this task must not break them."""
    import pdf_to_scouts

    assert hasattr(pdf_to_scouts, "cv2")
    assert callable(pdf_to_scouts.decode_variants)


def test_pdf_to_scouts_decode_embedded_qr_is_the_adapters_from_page_body() -> None:
    """One implementation, two entry points: pdf_to_scouts.decode_embedded_qr(document, page,
    detector) must be the SAME object as the adapter's decode_embedded_qr_from_page, not a
    second copy of the logic that could drift from it."""
    import pdf_to_scouts

    from scoutmb.adapters.pdf.extract import decode_embedded_qr_from_page

    assert pdf_to_scouts.decode_embedded_qr is decode_embedded_qr_from_page


def test_pdf_to_scouts_scoutingevent_prefix_is_the_adapters_single_copy() -> None:
    """Must be imported, not a second literal that could desync from the adapter's copy."""
    import pdf_to_scouts

    from scoutmb.adapters.pdf.extract import SCOUTINGEVENT_PREFIX

    assert pdf_to_scouts.SCOUTINGEVENT_PREFIX is SCOUTINGEVENT_PREFIX


def test_private_stack_guard_also_fails_closed() -> None:
    """Blocking the real import is stronger than monkeypatching the error path: it proves the
    guard converts a REAL ImportError, not a stub."""
    probe = """
import json
import sys

src, = sys.argv[1:]
sys.path.insert(0, src)


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"cv2", "fitz", "numpy"}:
            raise ImportError("blocked")
        return None


sys.meta_path.insert(0, _Blocker())
from scoutmb.adapters.pdf.extract import _import_pdf_stack
from scoutmb.errors import CapabilityUnavailable

try:
    _import_pdf_stack()
    result = {"raised": None}
except CapabilityUnavailable as exc:
    result = {"raised": "CapabilityUnavailable", "message": str(exc)}
except Exception as exc:
    result = {"raised": type(exc).__name__, "message": str(exc)}
sys.stdout.write(json.dumps(result))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(SRC)],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    assert payload["raised"] == "CapabilityUnavailable", payload
    assert "scoutmb[pdf]" in payload["message"]
