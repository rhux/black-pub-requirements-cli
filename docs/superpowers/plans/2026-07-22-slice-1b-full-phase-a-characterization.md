# Slice 1b — Full Phase A Characterization (IN PROGRESS)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers-extended-cc:executing-plans. Steps use checkbox (`- [ ]`) syntax; the `.tasks.json` sidecar is the machine-readable source.

**Status:** IN PROGRESS — core tasks authored and runnable; the **exhaustive rows** flagged in each task's *Completeness checklist* still need adding before **Gate 1b**. Do not treat as READY until every checklist item is a concrete runnable row.
**Spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Companion:** `2026-07-22-slice-1a-in-place-correctness.md` (the in-place fixes; must reach **Gate 1a** first — or run in parallel, since 1b is read-only characterization).
**Slice:** 1b of 5.

## Purpose

1b builds the **exhaustive Phase A behavior matrix** — the parity oracle Slice 2 diffs against
when it moves the input/PDF, scraper, output-writer, run-lifecycle, local-web, and bootstrap
code behind ports. Slice 1a self-guarded its own in-place changes; 1b pins *everything* so
that Slice 2's `parity` tests have a complete "before" to compare to. **Gate 1b — not Gate
1a — is what unblocks Slice 2.**

These are characterization tests: they record what the code does **today**, including awkward
or insecure behavior, classified `preserve` / `intentional-change` / `new-acceptance`. A test
that pins an exact legacy value carries a "confirm against the observed run" note — inherent
to characterization, not a placeholder.

## Dependencies on 1a

1b reuses 1a's tooling: `pyproject.toml`/`uv.lock` (Task 1a-1), the offline conftest (1a-3),
the synthetic factories (1a-4), the privacy tripwire (1a-5), and the `_Browser`/`_Resp` fakes
(moved to `tests/fakes/` per the review). Run `uv sync --locked --all-extras` — the
characterization suite imports `scout_schedule_cli`, which imports Playwright + openpyxl at
module scope.

## Completeness contract

Each task below is authored with **representative, runnable** rows plus a **Completeness
checklist** of the exhaustive rows the full matrix requires (XLSX/text loaders, dedup,
recursive/glob expansion, strict mode, corrupt PDF, rendered-QR fallback; zero-class and
transient-retry ScoutingEvent cases; every `summary.json` key and `report.html` structure;
`pdf_to_scouts.parse_args`; SSE framing and terminal events; the `--quiet` defect at
`pdf_to_scouts.py:571`; valid/invalid bootstrap markers). Gate 1b requires every checklist
box ticked with a concrete assertion.

---

### Task 16: Characterize the full input & PDF matrix (A7)

**Goal:** A table-driven suite pinning every input format and PDF-extraction behavior:
XLSX/CSV/JSON/text loading, directory/glob expansion, header aliases, dedup, QR decode
tiers, the exact 7-column attendee CSV schema, ordering, strict mode, corrupt input, and
optional-capability absence.

**Files:**
- Create: `tests/characterization/test_input_matrix.py`, `tests/characterization/test_pdf_matrix.py`
- Create: `tests/factories/pdf_builder.py` (synthetic PDF+QR generator, never committed as a binary)

**Acceptance Criteria:**
- [ ] `load_inputs` pinned for CSV, XLSX, JSON, and text, including every header alias in `first_matching_key`
- [ ] `expand_pdf_inputs` pinned for a file, a directory, a glob, and `--recursive`
- [ ] `decode_embedded_qr`/`extract_pdf` pinned against a **generated** synthetic PDF (raster QR); the rendered-fallback path noted for extension
- [ ] The exact 7 attendee columns asserted literally: `Attendee Name`, `Registrant Type`, `QR Code Contents`, `Name as Printed`, `Source PDF`, `PDF Page`, `QR Decode Method`
- [ ] Core-only import: `load_csv` works without `openpyxl`/`fitz`/`cv2` importable (optional-capability absence)

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/characterization/test_input_matrix.py tests/characterization/test_pdf_matrix.py -q`

**Steps:**

- [ ] **Step 1: Synthetic PDF builder** (uses `cv2.QRCodeEncoder` — OpenCV is already the `pdf` extra — + PyMuPDF `insert_image`; commit the builder, never a `.pdf`)

```python
# tests/factories/pdf_builder.py
"""Build a synthetic schedule PDF with an embedded QR, at test time. Never commit a .pdf."""

from __future__ import annotations

from pathlib import Path


def build_schedule_pdf(path: Path, *, name: str, registrant: str, qr_value: str) -> Path:
    import cv2  # from the `pdf` extra
    import fitz  # PyMuPDF
    import numpy as np

    encoder = cv2.QRCodeEncoder.create()
    qr = encoder.encode(qr_value)               # small binary image
    qr = cv2.resize(qr, (300, 300), interpolation=cv2.INTER_NEAREST)
    png = cv2.imencode(".png", qr)[1].tobytes()

    doc = fitz.open()
    page = doc.new_page()
    # value_after_label(lines, "Attendee Information") returns the line AFTER the label, so
    # the name/registrant values must be on their own separate lines beneath the labels
    # (pdf_to_scouts.py:176-192). Each insert_text at a distinct y is a separate text line.
    page.insert_text((72, 72), "Attendee Information")
    page.insert_text((72, 96), name)
    page.insert_text((72, 120), "Registrant")
    page.insert_text((72, 144), registrant)
    page.insert_image(fitz.Rect(72, 170, 372, 470), stream=png)
    doc.save(path)
    doc.close()
    return path
```

> The `numpy` import is unused above — drop it (ruff `F401`). Verify the two labels
> (`"Attendee Information"`, `"Registrant"`) against `extract_page_identity` before running;
> `value_after_label` matches the label line then takes the next non-empty line.

- [ ] **Step 2: Input-matrix characterization** (harness + representative rows; complete the
  alias/format table from observed `load_inputs` output — this is characterization)

```python
# tests/characterization/test_input_matrix.py
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402


# load_inputs (scout_schedule_cli.py:210) keeps ONLY urls starting with this prefix;
# anything else is silently dropped and an all-dropped file raises ValueError. Every
# fixture URL must therefore be a real scoutingevent.com/mobile URL (synthetic token).
QR = "https://scoutingevent.com/mobile/?t=TESTTOKEN0001"


def _csv(tmp_path, header, row):
    p = tmp_path / "in.csv"
    p.write_text(header + "\n" + row + "\n", encoding="utf-8")
    return p


@pytest.mark.parametrize(
    ("header", "expected_name_field"),
    [
        ("Attendee Name,QR Code Contents", "Avery Archer"),
        ("Name,QR Code Contents", "Avery Archer"),          # alias
        ("attendee name,qr code contents", "Avery Archer"),  # case/alias
        # These three rows are complete and runnable. Optionally extend with any further
        # alias `first_matching_key` accepts (read it in scout_schedule_cli.py); each added
        # row is one more characterization assertion.
    ],
)
def test_csv_header_aliases(tmp_path, header, expected_name_field):
    path = _csv(tmp_path, header, f"Avery Archer,{QR}")
    scouts = cli.load_inputs(path, sheet_name="Scouts Only", include_adults=True)
    assert scouts[0].name == expected_name_field


def test_json_loader(tmp_path):
    j = tmp_path / "in.json"
    j.write_text(json.dumps([{"Attendee Name": "Avery Archer", "QR Code Contents": QR}]),
                 encoding="utf-8")
    assert cli.load_inputs(j, "Scouts Only", True)[0].name == "Avery Archer"


def test_adult_filtering_default(tmp_path):
    # An adult-only file: excluded -> everything filtered -> load_inputs RAISES ValueError
    # (scout_schedule_cli.py:219 "No ScoutingEvent QR URLs found"); included -> 1 scout.
    path = _csv(tmp_path, "Attendee Name,Registrant Type,QR Code Contents",
                f"Adult Leader,Adult,{QR}")
    with pytest.raises(ValueError):
        cli.load_inputs(path, "Scouts Only", include_adults=False)
    assert len(cli.load_inputs(path, "Scouts Only", include_adults=True)) == 1
```

- [ ] **Step 3: PDF-matrix characterization** (`expand_pdf_inputs` + a generated PDF)

```python
# tests/characterization/test_pdf_matrix.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytest.importorskip("fitz"); pytest.importorskip("cv2")
import pdf_to_scouts as pdf  # noqa: E402
from tests.factories.pdf_builder import build_schedule_pdf  # noqa: E402


def test_expand_pdf_inputs_file_dir_glob(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    assert len(pdf.expand_pdf_inputs([str(tmp_path)], recursive=False)) == 2
    assert len(pdf.expand_pdf_inputs([str(tmp_path / "*.pdf")], recursive=False)) == 2


def test_embedded_qr_decodes_from_a_generated_pdf(tmp_path):
    token = "https://scoutingevent.com/mobile/?t=TESTTOKEN0001"
    p = build_schedule_pdf(tmp_path / "s.pdf", name="Avery Archer", registrant="Youth", qr_value=token)
    # Real signature (pdf_to_scouts.py:382): extract_pdf(pdf_path, dpis, normalize_case, debug_dir)
    attendees, errors = pdf.extract_pdf(p, dpis=[144], normalize_case=False, debug_dir=None)
    assert errors == []
    assert attendees[0].qr_data == token          # field is qr_data, not qr_value
    # Rendered-fallback path (vector QR -> decode_rendered_qr) is a follow-up row; note it.


def test_attendee_csv_has_exact_seven_columns(tmp_path):
    import csv
    from pdf_to_scouts import ExtractedAttendee, write_attendees_csv
    # Real ExtractedAttendee fields (pdf_to_scouts.py:27-35): attendee_name, name_as_printed,
    # registrant_type, qr_data, source_pdf, pdf_page, qr_decode_method.
    a = ExtractedAttendee(
        attendee_name="Avery Archer", name_as_printed="Avery Archer", registrant_type="Youth",
        qr_data="https://example.invalid/?t=TESTTOKEN0001",
        source_pdf="s.pdf", pdf_page=1, qr_decode_method="embedded",
    )
    out = tmp_path / "scouts.csv"
    write_attendees_csv(out, [a])
    with out.open(encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    # Real header (pdf_to_scouts.py:450-458) — DictWriter, 7 columns in this exact order:
    assert header == ["Attendee Name", "Registrant Type", "QR Code Contents",
                      "Name as Printed", "Source PDF", "PDF Page", "QR Decode Method"]
```

> **Signatures verified against `pdf_to_scouts.py`** (a `/codex` review caught the earlier
> draft's wrong parameter and field names). Still confirm `extract_page_identity` parses
> the builder's page text ("Attendee Information" / "Name …" / "Registrant …") — if not,
> adjust the builder's layout to what `value_after_label` expects. This is characterization.

- [ ] **Step 4: Run + complete the tables from observed output, then commit**

```bash
uv sync --extra pdf
uv run pytest tests/characterization/test_input_matrix.py tests/characterization/test_pdf_matrix.py -q
git add tests/characterization/test_input_matrix.py tests/characterization/test_pdf_matrix.py tests/factories/pdf_builder.py
git commit -m "test: characterize full input and PDF extraction matrix (A7)"
```

---

### Task 17: Characterize the ScoutingEvent payload & retry/error contract (A8, monkeypatch)

**Goal:** Pin the observed schedule/requirement payload shapes, the dedup rule, and the
retry/terminal-error behavior — via the monkeypatched module functions and synthetic
payloads. (The loopback **fake service** and real-Playwright-surface check are Slice 2.)

**Files:**
- Create: `tests/characterization/test_scoutingevent_contract.py`

**Acceptance Criteria:**
- [ ] Schedule payload variants pinned: zero classes, multiple classes, a `HAS_REQUIREMENTS=0` class
- [ ] The "prefer the completed duplicate" dedup rule (`scout_schedule_cli.py:510`) pinned with a duplicate-`classP4ID` payload
- [ ] Retry/error matrix pinned: transient-then-success, terminal error accumulates and does not raise
- [ ] A requirement payload missing an expected field is pinned as **current** behavior (drift handling is Slice 2/B4)

**Verify:** `uv run pytest tests/characterization/test_scoutingevent_contract.py -q`

**Steps:**

- [ ] **Step 1: Contract characterization** (reuse the fakes/monkeypatch pattern from Task 9)

```python
# tests/characterization/test_scoutingevent_contract.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402
from tests.characterization.test_process_scout import _Browser, _Resp  # noqa: E402
from tests.factories.payloads import requirement_payload, schedule_payload  # noqa: E402


def _args():
    return argparse.Namespace(timeout=45, request_delay_ms=0, allow_dead_assets=True,
                              headed=False, channel=None)


def _class(p4id, completed, has_req="1"):
    # Field names process_scout actually reads (scout_schedule_cli.py:515-529).
    return {"classP4ID": p4id, "CLASS_NAME": f"MoTuWeTh - Chess - {p4id}",
            "CLASS_NAME_ONLY": "Chess", "CLASS_NBR": "26MB1", "PERIOD_NAME": "A Block",
            "CLASS_STIME": "09:00 AM", "STIME": "09:00:00", "LOCATION_ROOM_NAME": "Pav",
            "HAS_REQ": has_req, "CLASS_COMPLETED": completed}


def _install(monkeypatch, schedule, requirement=None, post=None):
    async def nav(page, url, t):
        return _Resp(schedule)
    async def name(page, fb):
        return fb
    async def default_post(page, aid, cpid):
        return requirement or requirement_payload()
    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", post or default_post)


async def test_dedup_prefers_completed_duplicate(monkeypatch, tmp_path):
    _install(monkeypatch, schedule_payload([_class("2000001", "0"), _class("2000001", "1")]))
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    # One class survives dedup, and it is the COMPLETED duplicate (:510).
    assert len(result.classes) == 1
    assert result.classes[0].class_completed is True


async def test_multiple_and_no_requirement_classes(monkeypatch, tmp_path):
    _install(monkeypatch, schedule_payload([_class("2000001", "0"), _class("2000002", "0", has_req="0")]))
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert len(result.classes) == 2  # both classes recorded regardless of HAS_REQ


async def test_terminal_error_accumulates_without_raising(monkeypatch, tmp_path):
    async def boom(page, aid, cpid):
        raise RuntimeError("requirement endpoint down")
    _install(monkeypatch, schedule_payload([_class("2000001", "0")]), post=boom)
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    # The class is still recorded; the requirement failure is captured, not raised.
    assert len(result.classes) == 1
    assert any("requirement request failed" in e for e in result.errors)


async def test_missing_completed_flag_coerces_to_false(monkeypatch, tmp_path):
    """Pin CURRENT behavior: truthy(None) is False, so a missing flag reads incomplete.
    Fail-closed drift handling is a Slice-2 intentional change, not here."""
    row = {"MDM_LKP_BADGE_REQ_ID": "r1", "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
           "MERIT_BADGE_NAME": "Chess", "REQ_NBR_WEB_DISPLAY": "#1", "REQ_DESCR": "x",
           "REQ_ON_EVENT": "1", "PRESENT_DAYS": "MoTuWeTh"}  # no COMPLETED_REQ_FLAG
    _install(monkeypatch, schedule_payload([_class("2000001", "0")]),
             requirement=requirement_payload([row]))
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert result.requirements[0].completed_requirement is False
```

> These are complete and runnable. If an observed value differs (e.g. an error-string
> substring), correct the expectation from the run — this is characterization, the code is
> the authority. Do not change production.

- [ ] **Step 2: Run + commit**

```bash
uv sync --locked --all-extras
uv run pytest tests/characterization/test_scoutingevent_contract.py -q
git add tests/characterization/test_scoutingevent_contract.py
git commit -m "test: characterize ScoutingEvent payload/dedup/retry contract (A8, monkeypatch)"
```

---

### Task 18: Characterize artifact schemas, interface defaults, and a baseline (A9)

**Goal:** Pin the remaining output schemas (beyond the CSV headers in Task 9), the CLI/UI
default configuration, and a **pre-refactor request-count baseline** — the "before"
reference the Slice 4 performance gate compares against. (Slice 1a already applied the atomic-write change; here the schemas are pinned exhaustively as the Slice-2 parity oracle.)

**Files:**
- Create: `tests/characterization/test_artifact_matrix.py`, `tests/characterization/test_interface_matrix.py`
- Create: `tests/performance/test_baseline.py`, `tools/measure_baseline.py`

**Acceptance Criteria:**
- [ ] `errors.csv` header, `scouts.json` top-level keys, and `summary.json` keys pinned
- [ ] `report.html` structure pinned by parsing the injected `<script type="application/json">` block (not byte-compare)
- [ ] `parse_args` defaults pinned for both CLIs; the UI's default `Namespace` field values pinned
- [ ] `test_request_count_growth_is_bounded`: process_scout issues 1 schedule request + 1 requirement request per requirement-bearing class (hard assertion), captured by `measure_baseline.py`

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/characterization/test_artifact_matrix.py tests/characterization/test_interface_matrix.py tests/performance/test_baseline.py -q`

**Steps:**

- [ ] **Step 1: Artifact-schema characterization**

```python
# tests/characterization/test_artifact_matrix.py
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import ScoutResult, write_outputs  # noqa: E402
from tests.factories.records import make_class, make_requirement  # noqa: E402


def _results():
    r = ScoutResult(name="Avery Archer", qr_url="https://example.invalid/?t=TESTTOKEN0001",
                    attendee_id="90000001")
    r.classes.append(make_class())
    r.requirements.append(make_requirement())
    return [r]


def test_output_artifact_schemas(tmp_path):
    out = tmp_path / "2026-07-19_2139"
    write_outputs(out, _results(), generate_html=True, generate_email_report=False)

    with (out / "errors.csv").open(encoding="utf-8-sig", newline="") as fh:
        assert next(csv.reader(fh)) == ["scout_name", "attendee_id", "error"]

    scouts = json.loads((out / "scouts.json").read_text(encoding="utf-8"))
    assert set(scouts[0]) == {"name", "qr_url", "attendee_id", "classes", "requirements", "errors"}

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert {"scouts_processed", "classes", "requirements", "html_report"} <= set(summary)


def test_report_html_embeds_parseable_json(tmp_path):
    out = tmp_path / "run"
    write_outputs(out, _results(), generate_html=True, generate_email_report=False)
    html = (out / "report.html").read_text(encoding="utf-8")
    m = re.search(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S)
    assert m, "report embeds a application/json data block"
    json.loads(m.group(1))  # the injected payload parses
```

- [ ] **Step 2: Interface-defaults characterization** (monkeypatch `sys.argv` — `parse_args`
  takes no `argv` and requires `--input`, so calling it "as-is" under pytest would consume
  pytest's argv or exit)

```python
# tests/characterization/test_interface_matrix.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402


def test_schedule_cli_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", "--input", "scouts.csv"])
    args = cli.parse_args()
    assert args.input == Path("scouts.csv")
    assert args.no_html is False          # HTML on by default
    assert args.sheet == "Scouts Only"    # pin the observed defaults; correct from the run


def test_schedule_cli_exposes_the_fields_the_ui_namespace_mirrors(monkeypatch):
    """ui/server.py hand-builds a Namespace with these fields; async_main reads them. Pin
    that the CLI parser produces the same attribute set, so the Slice-2 ScrapeConfig can be
    parity-checked against one contract."""
    monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", "--input", "scouts.csv"])
    args = cli.parse_args()
    for field in ("input", "sheet", "output", "headed", "timeout", "no_html", "html_name"):
        assert hasattr(args, field), f"parse_args must expose {field}"
```

> The UI builds its `Namespace` inline in `ui/server.py:start_schedule_download`; there is
> nothing importable to assert directly without a refactor (that refactor is Slice 2). Pinning
> that `parse_args()` exposes the same field set is the parity anchor. Correct the field list
> against the observed `parse_args` output and the UI's construction.

- [ ] **Step 3: Request-count baseline**

```python
# tests/performance/test_baseline.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402
from tests.characterization.test_process_scout import _Browser, _Resp  # noqa: E402
from tests.factories.payloads import requirement_payload, schedule_payload  # noqa: E402


async def test_request_count_growth_is_bounded(monkeypatch, tmp_path):
    counts = {"schedule": 0, "requirement": 0}

    async def nav(page, url, t):
        counts["schedule"] += 1
        return _Resp(schedule_payload([
            {"classP4ID": "2000001", "CLASS_NAME_ONLY": "Chess", "CLASS_NBR": "26MB1",
             "HAS_REQ": "1", "CLASS_COMPLETED": "0"},
            {"classP4ID": "2000002", "CLASS_NAME_ONLY": "Art", "CLASS_NBR": "26MB2",
             "HAS_REQ": "1", "CLASS_COMPLETED": "0"}]))

    async def name(page, fb):
        return fb

    async def post(page, aid, cpid):
        counts["requirement"] += 1
        return requirement_payload()

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", post)

    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    args = argparse.Namespace(timeout=45, request_delay_ms=0, allow_dead_assets=True,
                              headed=False, channel=None)
    await cli.process_scout(_Browser(), scout, args, tmp_path)
    # 1 schedule request + 1 requirement request per requirement-bearing class. Hard bound.
    assert counts == {"schedule": 1, "requirement": 2}
```

  `tools/measure_baseline.py` runs the same flow and writes `build/baseline.json`
  (`{"machine_class": ..., "schedule_requests": 1, "requirement_requests_per_class": 1}`),
  the "before" reference for the Slice-4 performance gate. No wall-time threshold yet.

- [ ] **Step 4: Run + commit**

```bash
uv sync --locked --all-extras
uv run pytest tests/characterization/test_artifact_matrix.py tests/characterization/test_interface_matrix.py tests/performance/test_baseline.py -q
uv run python tools/measure_baseline.py --output build/baseline.json
git add tests/characterization/test_artifact_matrix.py tests/characterization/test_interface_matrix.py tests/performance/test_baseline.py tools/measure_baseline.py
git commit -m "test: characterize artifact schemas, interface defaults, and request-count baseline (A9)"
```

---

### Task 19: Characterize bootstrap, local web, run lifecycle, and static UI (A10)

**Goal:** Pin the installer/bootstrap, local-web, run-lifecycle, and user-visible
progress/quiet/error behavior so Slice 2 can move them under parity. **Records current
behavior, including insecure/incomplete web behavior, as `preserve` /
`intentional-change` / `new-acceptance` — not as the final contract.** (Slice 1a already applied the data_root rewire and smoked the read routes; here the full bootstrap/web/lifecycle contract is pinned as the Slice-2 parity oracle.)

**Files:**
- Create: `tests/characterization/test_bootstrap_matrix.py`, `tests/characterization/test_local_web_matrix.py`, `tests/characterization/test_run_lifecycle_matrix.py`

**Acceptance Criteria:**
- [ ] Bootstrap: `paths.get_paths` and `marker.is_environment_valid` pinned for present/absent/invalid marker (importing `bootstrap.marker`/`bootstrap.paths` directly, **never** `bootstrap.main`, which pulls `winreg`)
- [ ] Local web (`TestClient`, in-process, `SCOUTMB_DEV=1` + a `tmp_path` data root so no installed dataset is touched): `/api/health`, `/api/status`, `/api/scouts` responses pinned
- [ ] Run lifecycle: pin that the API exposes **pause/resume only** and has **no cancel endpoint** (an absence characterization, so a Slice-2 cancel addition is a visible change)
- [ ] Static UI: the server-emitted SSE event `type` values the JS consumes are pinned; JS-only rendering is a documented observation, not asserted

**Verify:** `uv sync --locked --all-extras && SCOUTMB_DEV=1 uv run pytest tests/characterization/test_bootstrap_matrix.py tests/characterization/test_local_web_matrix.py tests/characterization/test_run_lifecycle_matrix.py -q`

**Steps:**

- [ ] **Step 1: Bootstrap characterization** — stdlib-only, importing only the leaf modules:

```python
# tests/characterization/test_bootstrap_matrix.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# Import ONLY the leaf modules. bootstrap.main imports bootstrap.webview2, whose
# module-level `import winreg` fails off-Windows; the winreg fix is Slice 4.
from bootstrap import marker, paths  # noqa: E402


def test_get_paths_uses_the_override_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path))
    p = paths.get_paths()
    assert tmp_path in p.app_dir.parents or p.app_dir == tmp_path / "app"


def test_missing_marker_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path))
    p = paths.get_paths()
    p.ensure_dirs()
    req = tmp_path / "requirements.txt"; req.write_text("fastapi\n", encoding="utf-8")
    assert marker.is_environment_valid(p, req) is False   # no marker -> invalid
```

> Confirm `AppPaths`'s real field names against `bootstrap/paths.py` before finalizing;
> adjust the assertion to the actual attribute (`app_dir`/`data_dir`).

- [ ] **Step 2: Local-web characterization** with `TestClient` (in-process ASGI, no real
  socket — the host-restriction conftest allows it):

```python
# tests/characterization/test_local_web_matrix.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Point the UI at a throwaway data root so no installed dataset is read or mutated.
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SCOUTMB_DEV", raising=False)
    import ui.server as server  # imported after env is set
    return TestClient(server.app)


def test_health_and_status(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    body = client.get("/api/status").json()
    assert body["scouts_csv_exists"] is False   # empty throwaway root


def test_scouts_missing_is_404(client):
    assert client.get("/api/scouts").status_code == 404
```

- [ ] **Step 3: Lifecycle + SSE + cancel-absence characterization**:

```python
# tests/characterization/test_run_lifecycle_matrix.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _routes():
    import ui.server as server
    return {getattr(r, "path", "") for r in server.app.routes}


def test_pause_and_resume_exist_but_cancel_does_not(monkeypatch, tmp_path):
    """Absence characterization: today there is pause/resume, NO cancel. A Slice-2 cancel
    endpoint would therefore be a visible, reviewed addition — not a silent one."""
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path))
    routes = _routes()
    assert "/api/schedule-download/pause" in routes
    assert "/api/schedule-download/resume" in routes
    assert not any("cancel" in r for r in routes)


def test_sse_event_types_the_frontend_consumes_are_stable():
    """The static JS switches on these SSE `type` strings (ui/static/app.js). Pin the set the
    server emits so Slice-2 changes to the event contract are caught."""
    src = (Path(__file__).resolve().parents[2] / "scout_schedule_cli.py").read_text(encoding="utf-8")
    for event_type in ("batch_start", "scout_start", "scout_done", "paused", "resumed"):
        assert f'"type": "{event_type}"' in src or f"'type': '{event_type}'" in src
```

> Confirm the exact route paths against `ui/server.py` and the emitted event `type` strings
> against `async_main`/the UI worker before finalizing. Correct any string from the source.

- [ ] **Step 4: Run + commit**

```bash
uv sync --locked --all-extras
uv run pytest tests/characterization/test_bootstrap_matrix.py tests/characterization/test_local_web_matrix.py tests/characterization/test_run_lifecycle_matrix.py -q
git add tests/characterization/test_bootstrap_matrix.py tests/characterization/test_local_web_matrix.py tests/characterization/test_run_lifecycle_matrix.py
git commit -m "test: characterize bootstrap, local web, lifecycle, and static-UI contract (A10)"
```

---

---

## Gate 1b — Full Phase A characterization go/no-go (unblocks Slice 2)

**Goal:** The complete legacy behavior matrix is pinned and classified, so Slice 2 can move
each module under parity.

**Verify (all must pass):**
```bash
uv sync --locked --all-extras
uv run ruff check . && uv run ruff format --check . && uv run mypy
SCOUTMB_DEV=1 uv run pytest -m "not live_service and not playwright" --cov=src/scoutmb --cov-branch -q
uv run python tools/check_private_data.py --corpus raw_data tests
```

**Expected GO:** every command exits 0; every *Completeness checklist* box across Tasks 16–19
is a concrete runnable assertion (no representative-only gaps); input/PDF, ScoutingEvent
contract, artifacts, interfaces, bootstrap, web, lifecycle, and static-UI behavior are each
pinned and classified `preserve`/`intentional-change`/`new-acceptance`; the request-count
baseline is recorded; `private-data findings: 0`.

**NO-GO:** stop, complete the missing rows, rerun. Slice 2 does **not** start until Gate 1b is
green — its parity suite has nothing to diff against otherwise.

## Self-review

**Coverage:** D8 (the exhaustive legacy behavior matrix) and D21 (the pre-refactor
request-count baseline). This is the parity oracle referenced by Slice 2's Gate 2.

**Honest status:** the four tasks carry corrected, runnable representative code (the codex
findings on PDF signatures, loader URLs, `parse_args`-via-argv, the cancel-endpoint absence,
and `measure_baseline` are fixed here). What remains is breadth — each Completeness checklist
enumerates the exhaustive rows still to author. This slice is deliberately marked IN PROGRESS
until those are filled; 1a is the READY unit.
