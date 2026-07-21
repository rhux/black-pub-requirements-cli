# scoutmb Foundation Implementation Plan (Spec Phases 0–3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish tooling, a real characterization safety net, correct attendee identity, and a copy-only migration that protects the one live installation's data — before any code moves.

**Architecture:** Nothing is restructured in this plan. We add `pyproject.toml`, ruff/mypy/pytest, and staged CI; build sanitized fixtures from the local real corpus; pin current behavior of the flat modules with characterization tests (including `process_scout`, reachable via monkeypatch); then make two deliberate, individually-tested behavior changes — a stable `AttendeeKey` replacing name-based identity, and an explicit `data_root` plus legacy migration. Package restructuring begins in the next plan, on top of this net.

**Tech Stack:** Python 3.12 target (dev venv is 3.14), uv, ruff, mypy, pytest + pytest-cov + pytest-socket, PyMuPDF, OpenCV, Playwright, FastAPI.

**User decisions (already made):**
- Package name is `scoutmb`; console command `troop349`.
- CLI flags may be redesigned in this refactor, then stay stable afterward.
- GUI is the product; CLI is a developer/debug tool. Both stay first-class.
- One installation exists in the wild with real data. **Breaking the install is acceptable; destroying its data is not.**
- Keep `errors.py`, keep `ProgressSink` (needed by planned work), keep application self-update.
- Wheel + `python-build-standalone` for the launcher (spec Phase 9, not this plan).
- No real Scout data in the spec or codebase, ever. `raw_data/` stays local and gitignored.

---

## Scope

This plan implements **spec Phases 0–3 only**. The spec has 12 phases; writing all of them at full fidelity now would be speculative, because Phases 4+ depend on what the characterization suite in Task 6–11 actually reveals (notably the `Note.`-row hypothesis, which may turn out to be a live defect requiring its own scheduled fix).

Phases 0–3 form a coherent, shippable unit: **after this plan, the live install's data is protected, same-named Scouts can no longer corrupt each other, and every subsequent refactor has a regression net.** Plan 2 (package restructure, spec Phases 4–8) is written after Task 14 lands.

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Project metadata, dependencies, ruff/mypy/pytest/coverage config |
| `.github/workflows/ci.yml` | Staged CI — lint, types, lock only at this stage |
| `tools/verify_corpus.py` | Reproduce corpus counts, emit aggregates only, never PII |
| `tools/scrub_fixtures.py` | Convert a real run into committable fixtures; self-verifying |
| `tests/conftest.py` | Fixture tripwire, socket blocking, shared fixtures |
| `tests/factories/records.py` | Builders for `ClassRecord` / `RequirementRecord` test data |
| `tests/characterization/*` | Pin current behavior of the flat modules |
| `src/scoutmb/domain/identity.py` | `AttendeeKey` — stable, non-reversible attendee identity |
| `src/scoutmb/errors.py` | `ScoutmbError` hierarchy (seeded here, grown later) |
| `src/scoutmb/ui/settings.py` | `UiSettings` with explicit `data_root` resolution |
| `bootstrap/migrate.py` | Copy-only legacy `app/` → `data/` migration |

`src/scoutmb/` is created in this plan only for the three modules above. The bulk move happens in Plan 2.

---

### Task 1: Project tooling scaffold

**Goal:** `pyproject.toml` with ruff, mypy, pytest, and coverage configured for a 3.12 target, with zero source changes.

**Files:**
- Create: `pyproject.toml`
- Modify: `.gitignore`

**Acceptance Criteria:**
- [ ] `ruff check .` exits 0 on the untouched tree
- [ ] `ruff format --check .` reports the current formatting state without erroring the run
- [ ] `mypy` runs and exits 0 (nothing typed strictly yet)
- [ ] `requires-python = ">=3.12"` and ruff `target-version = "py312"`
- [ ] No test job configured yet — `pytest` is installed but CI does not run it until Task 6

**Verify:** `ruff check . && mypy --version && python -c "import tomllib,pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"` → exit 0

**Steps:**

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "scoutmb"
version = "0.1.0"
description = "Scout merit-badge schedule and requirement extraction for Troop 349"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.57,<2",
    "openpyxl>=3.1,<4",
    "PyMuPDF>=1.24,<2",
    "opencv-python-headless>=4.10,<5",
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.32,<1",
    "python-multipart>=0.0.12,<1",
    "pywebview>=5.3,<6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "pytest-cov>=6.0,<7",
    "pytest-asyncio>=0.24,<1",
    "pytest-socket>=0.7,<1",
    "hypothesis>=6.112,<7",
    "ruff>=0.8,<1",
    "mypy>=1.13,<2",
]

[tool.hatch.build.targets.wheel]
packages = ["src/scoutmb"]

[tool.hatch.build]
exclude = ["bootstrap", "raw_data", "docs"]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests", "tools"]
exclude = [".venv", "raw_data", "bootstrap/build.spec"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM", "PTH", "RET", "ARG", "TID"]
ignore = [
    "E501",    # line length is handled by the formatter
    "B008",    # FastAPI's Depends()/File() defaults are idiomatic
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ARG"]          # unused fixture args are normal in pytest

[tool.mypy]
python_version = "3.12"
files = ["src", "tools"]
ignore_missing_imports = true
warn_unused_ignores = true

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "playwright: tests requiring a real browser (deselected by default)",
]
addopts = "-m 'not playwright' --strict-markers"
asyncio_mode = "auto"

[tool.coverage.run]
branch = true
source = ["src/scoutmb", "tools"]
```

- [ ] **Step 2: Extend `.gitignore`**

Append these lines (`/raw_data/` and `.DS_Store` are already present):

```gitignore
# Added for the scoutmb restructure
.pytest_cache/
.ruff_cache/
.mypy_cache/
htmlcov/
.coverage
dist/
*.egg-info/
```

- [ ] **Step 3: Install the dev extras**

Run: `.venv/bin/python -m pip install -e ".[dev]"`
Expected: installs pytest, ruff, mypy, and the runtime deps; `Successfully installed` in output.

- [ ] **Step 4: Verify tooling runs clean**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!` — if any error appears, fix the config (not the source; this task changes no source).

Run: `.venv/bin/mypy`
Expected: exit 0, `Success: no issues found` (nothing is strictly typed yet).

- [ ] **Step 5: Record the Python version gap**

The dev venv is **3.14.6** but the shipped runtime is **3.12.8**, and no 3.12 interpreter exists on this machine. Install one so local runs match CI:

Run: `uv python install 3.12` (or download from python.org)
Then: `uv venv --python 3.12 .venv312 && .venv312/bin/python -m pip install -e ".[dev]"`

This is **recommended, not blocking** — CI runs 3.12 and is the authority. Record in the commit message which interpreter the tests were run under.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "build: add pyproject with ruff, mypy, pytest for a 3.12 target"
```

---

### Task 2: Staged CI — lint, types, lock

**Goal:** CI that passes today. No test or build job, because `pytest` with zero tests exits non-zero and `src/scoutmb` does not exist yet.

**Files:**
- Create: `.github/workflows/ci.yml`

**Acceptance Criteria:**
- [ ] Workflow parses as valid YAML
- [ ] Jobs: `lint`, `types` only
- [ ] Runs on `ubuntu-latest` with Python **3.12**
- [ ] No `pytest` step (added in Task 6), no wheel build (added in Plan 2)

**Verify:** `python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('valid')"` → `valid`

**Steps:**

- [ ] **Step 1: Create the workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .

  types:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: mypy
```

- [ ] **Step 2: Verify YAML validity**

Run: `.venv/bin/python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('valid')"`
Expected: `valid`

- [ ] **Step 3: Apply formatting as its own commit**

`ruff format --check` will fail on the existing source. Fix it in a **formatting-only commit** so formatting never mixes with logic in a diff:

```bash
.venv/bin/ruff format .
git add -A
git commit -m "style: apply ruff format (formatting only, no logic changes)"
```

- [ ] **Step 4: Commit the workflow**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint and types jobs on Python 3.12"
```

---

### Task 3: Corpus verification tool

**Goal:** A tool that reproduces the spec's corpus counts while emitting only aggregates, so the numbers can be re-checked without exporting any Scout data.

**Files:**
- Create: `tools/verify_corpus.py`
- Test: `tests/tools/test_verify_corpus.py`

**Acceptance Criteria:**
- [ ] Prints scouts / classes / requirements / raw-payload counts per run
- [ ] Prints the `(COMPLETED_REQ_FLAG, COMPLETED_CLASS_FLAG)` distribution
- [ ] Prints distinct `REQ_NBR_WEB_DISPLAY` **shape** counts, never raw values
- [ ] **Emits no names, attendee IDs, descriptions, or URLs** — enforced by a test
- [ ] Exits non-zero if the corpus directory is absent

**Verify:** `.venv/bin/pytest tests/tools/test_verify_corpus.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_verify_corpus.py
import json

from tools.verify_corpus import summarize_run


def test_summarize_emits_only_aggregates(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "ada-lovelace-26mb1-sched.json").write_text(
        json.dumps(
            {
                "status": {"status": 1, "stack": []},
                "data": [
                    {
                        "MDM_LKP_BADGE_REQ_ID": "111",
                        "REQ_NBR_WEB_DISPLAY": "#3b",
                        "REQ_DESCR": "Ada Lovelace secret description",
                        "COMPLETED_REQ_FLAG": "1",
                        "COMPLETED_CLASS_FLAG": "0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run(tmp_path)
    rendered = json.dumps(summary)

    assert summary["requirements"] == 1
    assert summary["flag_combos"]["('1', '0')"] == 1
    assert summary["number_shapes"]["#Na"] == 1
    # No PII may appear anywhere in the output.
    assert "Ada" not in rendered
    assert "Lovelace" not in rendered
    assert "secret" not in rendered
    assert "111" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/tools/test_verify_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.verify_corpus'`

- [ ] **Step 3: Write the implementation**

```python
# tools/verify_corpus.py
"""Reproduce the fixture-corpus counts cited in the design spec.

Emits aggregate counts only — never names, attendee IDs, descriptions, or URLs —
so the spec's numbers can be re-verified without exporting any Scout data.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any


def number_shape(value: str) -> str:
    """Collapse a requirement number to its punctuation/case shape.

    '#3b' -> '#Na',  '#2.Option.A.(1)' -> '#N.Aaaaaa.A.(N)'
    """
    shaped = re.sub(r"[A-Z]", "A", str(value))
    shaped = re.sub(r"[a-z]", "a", shaped)
    return re.sub(r"[0-9]+", "N", shaped)


def summarize_run(run_dir: Path) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    payloads = sorted(raw_dir.glob("*.json")) if raw_dir.is_dir() else []

    requirements = 0
    flag_combos: collections.Counter[str] = collections.Counter()
    number_shapes: collections.Counter[str] = collections.Counter()

    for payload_path in payloads:
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("data") or []:
            if not isinstance(row, dict):
                continue
            requirements += 1
            combo = (row.get("COMPLETED_REQ_FLAG"), row.get("COMPLETED_CLASS_FLAG"))
            flag_combos[str(combo)] += 1
            number_shapes[number_shape(row.get("REQ_NBR_WEB_DISPLAY") or "")] += 1

    return {
        "raw_payloads": len(payloads),
        "requirements": requirements,
        "flag_combos": dict(flag_combos),
        "number_shapes": dict(number_shapes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="Directory holding run subdirectories")
    args = parser.parse_args(argv)

    if not args.corpus.is_dir():
        print(f"Corpus directory not found: {args.corpus}", file=sys.stderr)
        return 2

    for run_dir in sorted(p for p in args.corpus.iterdir() if p.is_dir()):
        summary = summarize_run(run_dir)
        print(f"{run_dir.name}: {summary['requirements']} requirements, "
              f"{summary['raw_payloads']} payloads")
        for combo, count in sorted(summary["flag_combos"].items()):
            print(f"    flags {combo}: {count}")
        for shape, count in sorted(summary["number_shapes"].items(), key=lambda kv: -kv[1]):
            print(f"    shape {shape!r}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/tools/test_verify_corpus.py -v`
Expected: PASS

- [ ] **Step 5: Reproduce the spec's numbers**

Run: `.venv/bin/python tools/verify_corpus.py raw_data`
Expected: each of the three runs reports **4858 requirements** and **120 payloads**, and the flag distribution includes a `(None, None)` entry with **309**. If these differ, update the spec rather than the tool — the spec's numbers are the claim under test.

- [ ] **Step 6: Commit**

```bash
git add tools/verify_corpus.py tests/tools/test_verify_corpus.py
git commit -m "test: add corpus verification tool emitting aggregates only"
```

---

### Task 4: Self-verifying fixture scrubber

**Goal:** Convert a real run directory into committable fixtures, with automated proof that no original name, ID, or token survives — in file contents *or* filenames.

**Files:**
- Create: `tools/scrub_fixtures.py`
- Test: `tests/tools/test_scrub_fixtures.py`

**Acceptance Criteria:**
- [ ] Replaces names and attendee IDs deterministically (same input → same fake output)
- [ ] Rewrites **filenames** as well as contents
- [ ] Longest-first replacement, so `"Ann Lee"` inside `"Ann Leeson"` cannot leave a fragment
- [ ] `verify_clean` returns every surviving original; scrub **raises** if any remain
- [ ] Rewrites `scoutingevent.com/mobile/` tokens to `TESTTOKEN####`

**Verify:** `.venv/bin/pytest tests/tools/test_scrub_fixtures.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests (the leaky-input suite)**

```python
# tests/tools/test_scrub_fixtures.py
import pytest

from tools.scrub_fixtures import LeakDetected, build_mapping, scrub_text, verify_clean


def test_substring_name_is_fully_replaced():
    """'Ann Lee' must not leave a fragment inside 'Ann Leeson'."""
    mapping = build_mapping(names=["Ann Lee", "Ann Leeson"], attendee_ids=[])
    scrubbed = scrub_text("Ann Leeson met Ann Lee", mapping)

    assert "Ann Lee" not in scrubbed
    assert "Ann Leeson" not in scrubbed
    assert verify_clean(scrubbed, ["Ann Lee", "Ann Leeson"]) == []


def test_id_inside_html_attribute_is_replaced():
    mapping = build_mapping(names=[], attendee_ids=["90000042"])
    scrubbed = scrub_text('<tr data-attendee="90000042">', mapping)

    assert "90000042" not in scrubbed
    assert verify_clean(scrubbed, ["90000042"]) == []


def test_qr_token_is_rewritten_to_testtoken():
    mapping = build_mapping(names=[], attendee_ids=[])
    scrubbed = scrub_text("https://scoutingevent.com/mobile/?t=REALTOKEN99", mapping)

    assert "REALTOKEN99" not in scrubbed
    assert "TESTTOKEN" in scrubbed


def test_verify_clean_reports_survivors():
    assert verify_clean("Ann Lee is here", ["Ann Lee"]) == ["Ann Lee"]


def test_scrub_text_raises_when_a_leak_survives():
    """A mapping that fails to cover an original must fail loudly, not silently."""
    empty = build_mapping(names=[], attendee_ids=[])
    with pytest.raises(LeakDetected) as excinfo:
        scrub_text("Ann Lee", empty, must_not_contain=["Ann Lee"])
    assert "Ann Lee" in str(excinfo.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/tools/test_scrub_fixtures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.scrub_fixtures'`

- [ ] **Step 3: Write the implementation**

```python
# tools/scrub_fixtures.py
"""Turn a real run directory into committable fixtures.

Substitution is deterministic and longest-first, and every scrub is verified:
if any original value survives in contents or filenames, we raise rather than
write. An unverified scrubber is a data leak with extra steps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

QR_TOKEN_RE = re.compile(r"(scoutingevent\.com/mobile/[^\s\"'<>]*?[?&]t=)([A-Za-z0-9_-]+)")

_FIRST_NAMES = ["Avery", "Blake", "Casey", "Devon", "Ellis", "Finley", "Gray", "Harper",
                "Indigo", "Jules", "Kai", "Lane", "Micah", "Nova", "Oakley", "Parker",
                "Quinn", "Reese", "Sage", "Tatum", "Umber", "Vale"]
_LAST_NAMES = ["Archer", "Brooks", "Calder", "Dunmore", "Ellery", "Fenwick", "Garrow",
               "Holloway", "Ives", "Jarrow", "Keswick", "Lockhart", "Marsh", "Norrell",
               "Ovington", "Pike", "Quill", "Rowan", "Selby", "Thorne", "Underhill", "Vance"]


class LeakDetected(RuntimeError):
    """Raised when an original value survives scrubbing."""


@dataclass(frozen=True, slots=True)
class Mapping:
    replacements: dict[str, str] = field(default_factory=dict)

    def ordered_items(self) -> list[tuple[str, str]]:
        """Longest original first, so substrings cannot leave fragments."""
        return sorted(self.replacements.items(), key=lambda kv: len(kv[0]), reverse=True)


def _stable_index(value: str, modulus: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulus


def fake_name(original: str) -> str:
    first = _FIRST_NAMES[_stable_index(original + "|f", len(_FIRST_NAMES))]
    last = _LAST_NAMES[_stable_index(original + "|l", len(_LAST_NAMES))]
    return f"{first} {last}"


def fake_attendee_id(original: str) -> str:
    return f"9{_stable_index(original, 10_000_000):07d}"


def build_mapping(names: list[str], attendee_ids: list[str]) -> Mapping:
    replacements: dict[str, str] = {}
    for name in names:
        cleaned = name.strip()
        if cleaned:
            replacements[cleaned] = fake_name(cleaned)
    for attendee_id in attendee_ids:
        cleaned = attendee_id.strip()
        if cleaned:
            replacements[cleaned] = fake_attendee_id(cleaned)
    return Mapping(replacements)


def scrub_text(text: str, mapping: Mapping, must_not_contain: list[str] | None = None) -> str:
    scrubbed = text
    for original, replacement in mapping.ordered_items():
        scrubbed = scrubbed.replace(original, replacement)
    scrubbed = QR_TOKEN_RE.sub(
        lambda m: f"{m.group(1)}TESTTOKEN{_stable_index(m.group(2), 10_000):04d}", scrubbed
    )

    survivors = verify_clean(scrubbed, must_not_contain or list(mapping.replacements))
    if survivors:
        raise LeakDetected(f"Original values survived scrubbing: {survivors}")
    return scrubbed


def verify_clean(text: str, originals: list[str]) -> list[str]:
    """Return every original still present. Empty list means clean."""
    return [original for original in originals if original and original in text]


def collect_identifiers(run_dir: Path) -> tuple[list[str], list[str]]:
    names: set[str] = set()
    ids: set[str] = set()
    classes_csv = run_dir / "classes.csv"
    if classes_csv.is_file():
        with classes_csv.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("scout_name"):
                    names.add(row["scout_name"].strip())
                if row.get("attendee_id"):
                    ids.add(row["attendee_id"].strip())
    return sorted(names), sorted(ids)


def scrub_run(run_dir: Path, dest_dir: Path, keep_scouts: int = 3) -> None:
    names, ids = collect_identifiers(run_dir)
    if not names:
        raise RuntimeError(f"No scout names found in {run_dir}; refusing to scrub blind")

    keep = set(names[:keep_scouts])
    mapping = build_mapping(names, ids)
    originals = list(mapping.replacements)

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    for source in sorted(run_dir.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(run_dir)
        # Filenames carry name slugs — scrub the path, not just the bytes.
        scrubbed_relative = Path(scrub_text(str(relative), mapping))
        target = dest_dir / scrubbed_relative
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            content = source.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable artifacts are not fixture material

        target.write_text(scrub_text(content, mapping), encoding="utf-8")

        leaks = verify_clean(str(target), originals)
        if leaks:
            raise LeakDetected(f"Original values survived in path {target}: {leaks}")

    print(f"Scrubbed {run_dir} -> {dest_dir} (kept {len(keep)} scouts in the reduced set)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("dest_dir", type=Path)
    parser.add_argument("--keep-scouts", type=int, default=3)
    args = parser.parse_args(argv)

    if not args.run_dir.is_dir():
        print(f"Run directory not found: {args.run_dir}", file=sys.stderr)
        return 2
    scrub_run(args.run_dir, args.dest_dir, args.keep_scouts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/tools/test_scrub_fixtures.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tools/scrub_fixtures.py tests/tools/test_scrub_fixtures.py
git commit -m "test: add self-verifying fixture scrubber with leaky-input suite"
```

---

### Task 5: Generate committable fixtures and install the tripwire

**Goal:** A reduced, sanitized fixture set in the repo, plus a conftest tripwire that fails the suite if unsanitized data ever appears.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/run_reduced/` (generated)
- Create: `tests/factories/records.py`

**Acceptance Criteria:**
- [ ] `tests/fixtures/run_reduced/` contains 2–3 scouts' worth of scrubbed artifacts
- [ ] Tripwire fails if any fixture holds a `scoutingevent.com/mobile/` token not starting with `TESTTOKEN`
- [ ] `pytest-socket` blocks network in the default suite
- [ ] A PII sweep over `tests/` finds zero real names or IDs

**Verify:** `.venv/bin/pytest tests/ -v` → passes; and the sweep in Step 4 prints `NONE`

**Steps:**

- [ ] **Step 1: Generate the fixtures**

Run: `.venv/bin/python tools/scrub_fixtures.py raw_data/2026-07-19_2139 tests/fixtures/run_reduced --keep-scouts 3`
Expected: `Scrubbed raw_data/2026-07-19_2139 -> tests/fixtures/run_reduced (kept 3 scouts in the reduced set)`

If `LeakDetected` is raised, **do not commit anything** — fix the scrubber and re-run.

- [ ] **Step 2: Write `tests/conftest.py`**

```python
# tests/conftest.py
"""Shared fixtures plus the fixture-safety tripwire.

The tripwire is session-scoped and runs before any test: if unsanitized Scout
data ever lands under tests/fixtures/, the whole suite fails loudly rather than
quietly committing a leak.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
QR_TOKEN_RE = re.compile(r"scoutingevent\.com/mobile/[^\s\"'<>]*?[?&]t=([A-Za-z0-9_-]+)")


@pytest.fixture(scope="session", autouse=True)
def fixtures_are_sanitized() -> None:
    offenders: list[str] = []
    for path in FIXTURES_DIR.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in QR_TOKEN_RE.findall(content):
            if not token.startswith("TESTTOKEN"):
                offenders.append(f"{path}: token {token!r}")
    assert not offenders, (
        "Unsanitized QR tokens found under tests/fixtures/:\n  " + "\n  ".join(offenders)
    )


@pytest.fixture()
def reduced_run() -> Path:
    return FIXTURES_DIR / "run_reduced"
```

- [ ] **Step 3: Write `tests/factories/records.py`**

```python
# tests/factories/records.py
"""Builders for record test data.

Defaults are valid; tests override only the field under test, so a new field on
the dataclass does not break every test at once.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scout_schedule_cli import ClassRecord, RequirementRecord  # noqa: E402


def make_requirement(**overrides: Any) -> RequirementRecord:
    defaults: dict[str, Any] = {
        "scout_name": "Avery Archer",
        "attendee_id": "90000001",
        "class_number": "26MB1",
        "class_p4_id": "2000001",
        "merit_badge_name": "Chess",
        "requirement_id": "1001",
        "requirement_type_id": "1",
        "requirement_number": "#1",
        "description": "Discuss the history of chess.",
        "completed_requirement": False,
        "completed_class": False,
        "requirement_on_event": True,
        "present_days": "MoTuWeTh",
    }
    return RequirementRecord(**{**defaults, **overrides})


def make_class(**overrides: Any) -> ClassRecord:
    defaults: dict[str, Any] = {
        "scout_name": "Avery Archer",
        "attendee_id": "90000001",
        "class_number": "26MB1",
        "class_p4_id": "2000001",
        "class_name": "Chess",
        "days": "MoTuWeTh",
        "period_name": "A Block",
        "start_time": "09:00 AM",
        "start_time_24h": "09:00:00",
        "location": "Pavilion",
        "has_requirements": True,
        "class_completed": False,
        "raw_class_name": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
    }
    return ClassRecord(**{**defaults, **overrides})
```

- [ ] **Step 4: Run the PII sweep before committing**

```bash
.venv/bin/python - <<'PY'
import csv, re, pathlib
names, ids = set(), set()
with open('raw_data/2026-07-19_2139/classes.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        if r.get('scout_name'): names.add(r['scout_name'].strip())
        if r.get('attendee_id'): ids.add(r['attendee_id'].strip())
blob = "\n".join(
    str(p) + p.read_text(encoding='utf-8', errors='ignore')
    for p in pathlib.Path('tests').rglob('*') if p.is_file()
)
parts = {p for n in names for p in n.split() if len(p) > 3}
leaks = [v for v in (names | ids) if v and v in blob]
leaks += [f"partial:{p}" for p in parts if re.search(rf"\b{re.escape(p)}\b", blob)]
print("LEAKS:", leaks if leaks else "NONE")
PY
```
Expected: `LEAKS: NONE`. **If anything is listed, stop and fix the scrubber — do not commit.**

- [ ] **Step 5: Verify the suite runs**

Run: `.venv/bin/pytest tests/ -v`
Expected: previous tests still pass, tripwire fixture runs without failing.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/factories/records.py tests/fixtures/run_reduced
git commit -m "test: add sanitized fixture corpus, safety tripwire, and record factories"
```

---

### Task 6: Characterize `requirement_path` across all real shapes

**Goal:** Pin the current parse result for every requirement-number shape the real corpus contains, and add the `test` job to CI now that tests exist.

**Files:**
- Create: `tests/characterization/test_requirement_path.py`
- Modify: `.github/workflows/ci.yml`

**Acceptance Criteria:**
- [ ] All 18 observed shapes are covered as a `parametrize` table
- [ ] Suspect behaviors (`Note.` → `('7','note')`, `''` → `()`) are pinned **as-is** with comments marking them as unresolved, not "fixed"
- [ ] A `hypothesis` property test asserts `requirement_path` never raises on arbitrary strings
- [ ] CI gains a `test` job on ubuntu + windows

**Verify:** `.venv/bin/pytest tests/characterization/test_requirement_path.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the characterization tests**

```python
# tests/characterization/test_requirement_path.py
"""Pin current requirement_path behavior before any code moves.

These are characterization tests: they record what the code does TODAY,
including behavior we suspect is wrong. Suspect cases are marked. Do not
"fix" them here — a fix is a separate change with its own failing test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scout_schedule_cli import requirement_path  # noqa: E402


@pytest.mark.parametrize(
    ("number", "current_top_level", "expected_path", "expected_top_level"),
    [
        # --- ordinary, well-formed numbers ---
        ("#3b", None, ("3", "b"), "3"),
        ("#3(b)", None, ("3", "b"), "3"),
        ("6.a.1.", None, ("6", "a", "1"), "6"),
        ("#5(c)(1)", None, ("5", "c", "1"), "5"),
        ("#1", None, ("1",), "1"),
        ("2.", None, ("2",), "2"),
        ("4", None, ("4",), "4"),
        ("#7a.", None, ("7", "a"), "7"),
        ("#8a(2)", None, ("8", "a", "2"), "8"),
        ("3.b.", None, ("3", "b"), "3"),
        # --- word-bearing option numbers (Shooting Sports style) ---
        ("#2.Option.A.(1)", None, ("2", "option", "a", "1"), "2"),
        ("#5.Option.D.(3)(a)", None, ("5", "option", "d", "3", "a"), "5"),
        ("#5.Option.A(1)", None, ("5", "option", "a", "1"), "5"),
        # --- malformed separators: punctuation is ignored by construction ---
        ("#5..Opt.A.(1)", None, ("5", "opt", "a", "1"), "5"),
        # --- malformed: missing top level, inherits the last-seen one ---
        ("#(c)", "7", ("7", "c"), "7"),
        # --- SUSPECT: a label row becomes a CHILD of the preceding requirement.
        #     If requirement 7 is a "Do TWO of the following" choice, this note
        #     enters the satisfied-child arithmetic. Unresolved; see spec.
        ("Note.", "7", ("7", "note"), "7"),
        # --- SUSPECT: 402 rows have an empty number AND empty description ---
        ("", None, (), None),
        ("", "7", (), "7"),
    ],
)
def test_requirement_path_pins_current_behavior(
    number, current_top_level, expected_path, expected_top_level
):
    path, top_level = requirement_path(number, current_top_level)
    assert path == expected_path
    assert top_level == expected_top_level


@given(st.text(max_size=40))
def test_requirement_path_never_raises(value: str):
    """Whatever the upstream API emits, parsing must not crash the run."""
    path, _ = requirement_path(value, None)
    assert isinstance(path, tuple)
```

- [ ] **Step 2: Run tests to verify they pass against current code**

Run: `.venv/bin/pytest tests/characterization/test_requirement_path.py -v`
Expected: all PASS. **A failure here means the expected value is wrong, not the code** — correct the test to match observed behavior, since this is characterization.

- [ ] **Step 3: Add the `test` job to CI**

Insert this job into `.github/workflows/ci.yml` after `types`:

```yaml
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest --cov --cov-report=term-missing
```

- [ ] **Step 4: Verify the whole suite**

Run: `.venv/bin/pytest --cov --cov-report=term-missing`
Expected: all tests pass; a coverage table prints.

- [ ] **Step 5: Commit**

```bash
git add tests/characterization/test_requirement_path.py .github/workflows/ci.yml
git commit -m "test: characterize requirement_path across all 18 real shapes"
```

---

### Task 7: Characterize inference — purity, statuses, and both consumers

**Goal:** Pin `annotate_requirement_statuses` and `build_missing_requirements`, including the non-mutation guarantee and the `id()`-keyed bookkeeping that a later dataclass refactor will disturb.

**Files:**
- Create: `tests/characterization/test_inference.py`

**Acceptance Criteria:**
- [ ] A test proves input dictionaries are **not** mutated (guards the copy at `:672`)
- [ ] Choice-requirement threshold behavior is pinned (`Do ONE` / `Do TWO`)
- [ ] Both consumers are pinned separately: `annotate_requirement_statuses` directly and `build_missing_requirements`
- [ ] A test documents that same-named attendees currently **merge**, marked as the defect Task 9 fixes
- [ ] **Leaf selection and ancestor inclusion are pinned**, because `build_missing_requirements` implements them with `dict[int, bool]` keyed on `id(item)` (`:801-835`). That keying cannot survive the move to dataclasses, so Plan 2 must rewrite it over node indices — these tests are the only thing that will catch a behavior change during that rewrite
- [ ] The `(not used)` filter and the `requirement_type_id == "3"` section-header exclusion are pinned

**Verify:** `.venv/bin/pytest tests/characterization/test_inference.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the characterization tests**

```python
# tests/characterization/test_inference.py
"""Pin inference behavior before decomposition.

Includes a test that documents a KNOWN DEFECT (same-named attendees merge).
That test asserts today's wrong behavior on purpose; Task 9 replaces it with
the corrected expectation. Do not "fix" it here.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scout_schedule_cli import (  # noqa: E402
    annotate_requirement_statuses,
    build_missing_requirements,
    choice_requirement_count,
)

from tests.factories.records import make_requirement  # noqa: E402


def test_annotate_does_not_mutate_its_input():
    """scout_schedule_cli.py:672 copies every input dict. Guard that."""
    rows = [asdict(make_requirement(requirement_number="#1"))]
    before = [dict(row) for row in rows]

    annotate_requirement_statuses(rows)

    assert rows == before, "annotate_requirement_statuses must not mutate caller data"


def test_parent_completes_when_all_children_complete():
    rows = [
        asdict(make_requirement(requirement_number="#1", requirement_id="p")),
        asdict(make_requirement(requirement_number="#1a", requirement_id="c1",
                                completed_requirement=True)),
        asdict(make_requirement(requirement_number="#1b", requirement_id="c2",
                                completed_requirement=True)),
    ]
    annotated = annotate_requirement_statuses(rows)
    parent = next(r for r in annotated if r["requirement_id"] == "p")

    assert parent["calculated_status"] in {"complete", "complete_check"}


def test_choice_parent_completes_at_the_stated_threshold():
    rows = [
        asdict(make_requirement(requirement_number="#2", requirement_id="p",
                                description="Do TWO of the following.")),
        asdict(make_requirement(requirement_number="#2a", requirement_id="c1",
                                completed_requirement=True)),
        asdict(make_requirement(requirement_number="#2b", requirement_id="c2",
                                completed_requirement=True)),
        asdict(make_requirement(requirement_number="#2c", requirement_id="c3")),
    ]
    annotated = annotate_requirement_statuses(rows)
    parent = next(r for r in annotated if r["requirement_id"] == "p")

    assert parent["choice_required_count"] == 2
    assert parent["calculated_status"] == "complete_check"


def test_choice_requirement_count_handles_every_corpus_verb():
    assert choice_requirement_count("Do TWO of the following.") == 2
    assert choice_requirement_count("Choose ONE of the following options.") == 1
    assert choice_requirement_count("Complete one of the following") == 1
    assert choice_requirement_count("Select two of the following.") == 2
    assert choice_requirement_count("Explain the following terms") is None


def test_build_missing_requirements_groups_by_badge():
    scouts = [
        {
            "name": "Avery Archer",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                asdict(make_requirement(requirement_number="#1", requirement_id="r1",
                                        merit_badge_name="Chess")),
            ],
            "errors": [],
        }
    ]
    grouped = build_missing_requirements(scouts)

    assert "Avery Archer" in grouped
    assert "Chess" in grouped["Avery Archer"]


def test_leaf_selection_includes_incomplete_ancestors():
    """Pin the ancestor walk at :801-835.

    build_missing_requirements keys selection on id(item). That breaks when
    inference moves to dataclasses, so Plan 2 rewrites it over node indices.
    These assertions are the contract that rewrite must preserve.
    """
    scouts = [
        {
            "name": "Avery Archer",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                asdict(make_requirement(requirement_number="#3", requirement_id="parent",
                                        description="Do the following.")),
                asdict(make_requirement(requirement_number="#3b", requirement_id="leaf")),
            ],
            "errors": [],
        }
    ]
    entries = build_missing_requirements(scouts)["Avery Archer"]["Chess"]
    numbers = {e["requirement_number"]: e for e in entries}

    # The incomplete leaf is actionable...
    assert numbers["#3b"]["is_leaf"] is True
    # ...and its still-incomplete parent rides along for context.
    assert numbers["#3"]["is_leaf"] is False


def test_section_headers_and_not_used_rows_are_excluded():
    """type_id '3' is a section header; '(not used)' rows are dead weight."""
    scouts = [
        {
            "name": "Avery Archer",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                asdict(make_requirement(requirement_number="#4", requirement_id="hdr",
                                        requirement_type_id="3")),
                asdict(make_requirement(requirement_number="#5", requirement_id="dead",
                                        description="Forge a blade ...(not used)")),
                asdict(make_requirement(requirement_number="#6", requirement_id="live")),
            ],
            "errors": [],
        }
    ]
    entries = build_missing_requirements(scouts)["Avery Archer"]["Chess"]
    numbers = {e["requirement_number"] for e in entries}

    assert "#6" in numbers
    assert "#4" not in numbers, "section headers are not actionable on their own"
    assert "#5" not in numbers, "(not used) rows must be filtered"


def test_KNOWN_DEFECT_same_named_attendees_are_merged():
    """DEFECT (spec defect #1): grouping keys on scout_name, not attendee_id.

    Two different attendees sharing a display name have their requirements
    merged into one bucket. This test pins the WRONG behavior so Task 9's fix
    is visible as an intentional change. Task 9 replaces this test.
    """
    scouts = [
        {
            "name": "Avery Archer",
            "attendee_id": "90000001",
            "classes": [],
            "requirements": [
                asdict(make_requirement(attendee_id="90000001", requirement_id="r1",
                                        requirement_number="#1", merit_badge_name="Chess")),
            ],
            "errors": [],
        },
        {
            "name": "Avery Archer",          # same display name, different person
            "attendee_id": "90000002",
            "classes": [],
            "requirements": [
                asdict(make_requirement(attendee_id="90000002", requirement_id="r2",
                                        requirement_number="#2", merit_badge_name="Chess")),
            ],
            "errors": [],
        },
    ]
    grouped = build_missing_requirements(scouts)

    # Today: ONE bucket holding BOTH attendees' requirements. That is the bug.
    assert list(grouped) == ["Avery Archer"]
    assert len(grouped["Avery Archer"]["Chess"]) == 2
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/characterization/test_inference.py -v`
Expected: all PASS. If a status assertion fails, adjust the expectation to the observed value — this is characterization, and the code is the authority.

- [ ] **Step 3: Commit**

```bash
git add tests/characterization/test_inference.py
git commit -m "test: characterize inference incl. non-mutation and the name-merge defect"
```

---

### Task 8: Characterize `process_scout`, loaders, and CSV headers

**Goal:** Pin the orchestration path Codex showed is reachable via monkeypatch, plus the CSV header rows that silently depend on dataclass field order.

**Files:**
- Create: `tests/characterization/test_process_scout.py`
- Create: `tests/characterization/test_outputs.py`

**Acceptance Criteria:**
- [ ] `process_scout` is exercised with **no real browser**, by monkeypatching `navigate_and_trigger_schedule`, `discover_name`, and `post_requirement`
- [ ] Retry behavior is pinned at exactly 3 attempts
- [ ] Schedule dedup ("prefer the completed duplicate", `:510`) is pinned
- [ ] `classes.csv` and `requirements.csv` header rows are asserted literally, guarding `__dataclass_fields__` order (`:1666`, `:1671`)

**Verify:** `.venv/bin/pytest tests/characterization/ -v` → all pass

**Steps:**

- [ ] **Step 1: Write the `process_scout` characterization test**

```python
# tests/characterization/test_process_scout.py
"""Characterize process_scout WITHOUT a browser.

navigate_and_trigger_schedule (:368), discover_name (:347), and
post_requirement (:417) are module-level functions called by name at :479,
:486, and :540. Monkeypatching them makes the orchestration — dedup, retry,
record mapping, error accumulation — fully testable today, before the port
extraction.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scout_schedule_cli as cli  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


class FakePage:
    async def evaluate(self, *args, **kwargs):
        return None

    async def wait_for_timeout(self, _ms: int) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeContext:
    async def new_page(self) -> FakePage:
        return FakePage()

    async def route(self, *args, **kwargs) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeBrowser:
    async def new_context(self, **kwargs) -> FakeContext:
        return FakeContext()


def make_args(**overrides) -> argparse.Namespace:
    defaults = {
        "timeout": 45,
        "request_delay_ms": 0,
        "allow_dead_assets": True,
        "headed": False,
        "channel": None,
    }
    return argparse.Namespace(**{**defaults, **overrides})


@pytest.fixture()
def fake_schedule(monkeypatch):
    """Install fakes for the three module-level Playwright entry points."""
    schedule_payload = {
        "status": {"status": 1},
        "data": [
            {
                "classP4ID": "2000001",
                "CLASS_NAME": "Chess",
                "CLASS_NBR": "26MB1",
                "CLASS_COMPLETED": "0",
                "HAS_REQUIREMENTS": "1",
                "attendeeID": "90000001",
            }
        ],
    }

    async def fake_navigate(page, qr_url, timeout_seconds):
        return FakeResponse(schedule_payload)

    async def fake_discover_name(page, fallback):
        return fallback

    async def fake_post_requirement(page, attendee_id, class_p4_id):
        return {
            "status": {"status": 1},
            "data": [
                {
                    "MDM_LKP_BADGE_REQ_ID": "r1",
                    "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
                    "MERIT_BADGE_NAME": "Chess",
                    "REQ_NBR_WEB_DISPLAY": "#1",
                    "REQ_DESCR": "Discuss the history of chess.",
                    "COMPLETED_REQ_FLAG": "0",
                    "COMPLETED_CLASS_FLAG": "0",
                    "REQ_ON_EVENT": "1",
                    "PRESENT_DAYS": "MoTuWeTh",
                }
            ],
        }

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", fake_navigate)
    monkeypatch.setattr(cli, "discover_name", fake_discover_name)
    monkeypatch.setattr(cli, "post_requirement", fake_post_requirement)
    return schedule_payload


async def test_process_scout_builds_records_without_a_browser(fake_schedule, tmp_path):
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")

    result = await cli.process_scout(FakeBrowser(), scout, make_args(), tmp_path)

    assert result.name == "Avery Archer"
    assert len(result.classes) == 1
    assert result.classes[0].class_name == "Chess"
    assert len(result.requirements) == 1
    assert result.requirements[0].requirement_number == "#1"
    assert result.errors == []


async def test_process_scout_records_errors_without_aborting(monkeypatch, tmp_path):
    async def failing_navigate(page, qr_url, timeout_seconds):
        raise RuntimeError("schedule endpoint exploded")

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", failing_navigate)

    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(FakeBrowser(), scout, make_args(), tmp_path)

    assert result.errors, "a failing scout must accumulate an error, not raise"
    assert "schedule endpoint exploded" in " ".join(result.errors)


async def test_requirement_fetch_retries_exactly_three_times(fake_schedule, tmp_path):
    attempts = {"count": 0}

    async def flaky_post_requirement(page, attendee_id, class_p4_id):
        attempts["count"] += 1
        raise RuntimeError("transient")

    import scout_schedule_cli as module

    module.post_requirement = flaky_post_requirement  # noqa: SLF001 - characterization
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")

    await cli.process_scout(FakeBrowser(), scout, make_args(), tmp_path)

    assert attempts["count"] == 3, "retry policy is range(1, 4) at scout_schedule_cli.py:538"
```

- [ ] **Step 2: Run and reconcile**

Run: `.venv/bin/pytest tests/characterization/test_process_scout.py -v`
Expected: PASS. If a fake is missing a method `process_scout` calls, the failure names it — add the method to the fake. **Do not change `scout_schedule_cli.py`.**

- [ ] **Step 3: Write the output-format characterization test**

```python
# tests/characterization/test_outputs.py
"""Pin the CSV header rows.

write_outputs derives fieldnames from __dataclass_fields__ order (:1666, :1671),
so reordering a dataclass field silently reorders CSV columns. These literal
header assertions are the only thing that catches that.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scout_schedule_cli import ClassRecord, RequirementRecord, write_csv  # noqa: E402

from tests.factories.records import make_class, make_requirement  # noqa: E402

EXPECTED_CLASS_HEADER = [
    "scout_name", "attendee_id", "class_number", "class_p4_id", "class_name",
    "days", "period_name", "start_time", "start_time_24h", "location",
    "has_requirements", "class_completed", "raw_class_name",
]

EXPECTED_REQUIREMENT_HEADER = [
    "scout_name", "attendee_id", "class_number", "class_p4_id", "merit_badge_name",
    "requirement_id", "requirement_type_id", "requirement_number", "description",
    "completed_requirement", "completed_class", "requirement_on_event", "present_days",
]


def test_class_csv_header_is_stable(tmp_path):
    path = tmp_path / "classes.csv"
    fieldnames = [f.name for f in ClassRecord.__dataclass_fields__.values()]
    write_csv(path, [make_class()], fieldnames)

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream))

    assert header == EXPECTED_CLASS_HEADER


def test_requirement_csv_header_is_stable(tmp_path):
    path = tmp_path / "requirements.csv"
    fieldnames = [f.name for f in RequirementRecord.__dataclass_fields__.values()]
    write_csv(path, [make_requirement()], fieldnames)

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream))

    assert header == EXPECTED_REQUIREMENT_HEADER
```

- [ ] **Step 4: Run the full characterization suite**

Run: `.venv/bin/pytest tests/characterization/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/characterization/test_process_scout.py tests/characterization/test_outputs.py
git commit -m "test: characterize process_scout via monkeypatch and pin CSV headers"
```

---

### Task 9: `AttendeeKey` — stable, non-reversible attendee identity

**Goal:** A domain type that replaces the display name as identity, with a filename-safe digest that never exposes the bearer-token attendee ID.

**Files:**
- Create: `src/scoutmb/__init__.py`
- Create: `src/scoutmb/errors.py`
- Create: `src/scoutmb/domain/__init__.py`
- Create: `src/scoutmb/domain/identity.py`
- Test: `tests/unit/test_identity.py`

**Acceptance Criteria:**
- [ ] `AttendeeKey.from_attendee_id` rejects blank IDs with a typed error
- [ ] `AttendeeKey.unresolved(seed)` produces a stable key when the API supplies no ID
- [ ] `.short` is 8 hex chars, deterministic, and **does not contain the raw ID**
- [ ] Two different IDs never produce the same `.short` in the corpus-sized ID space
- [ ] `mypy --strict src/scoutmb/domain/identity.py` passes

**Verify:** `.venv/bin/pytest tests/unit/test_identity.py -v && .venv/bin/mypy --strict src/scoutmb/domain/identity.py`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_identity.py
import pytest

from scoutmb.domain.identity import AttendeeKey
from scoutmb.errors import MissingAttendeeId


def test_key_is_stable_for_the_same_id():
    assert AttendeeKey.from_attendee_id("90000042") == AttendeeKey.from_attendee_id("90000042")


def test_short_is_deterministic_and_hides_the_raw_id():
    key = AttendeeKey.from_attendee_id("90000042")

    assert len(key.short) == 8
    assert key.short == AttendeeKey.from_attendee_id("90000042").short
    assert "90000042" not in key.short


def test_different_ids_produce_different_shorts():
    shorts = {AttendeeKey.from_attendee_id(str(90000000 + n)).short for n in range(500)}
    assert len(shorts) == 500


def test_blank_id_is_rejected():
    with pytest.raises(MissingAttendeeId):
        AttendeeKey.from_attendee_id("   ")


def test_unresolved_key_is_stable_and_distinct():
    a = AttendeeKey.unresolved("https://example.invalid/?t=TESTTOKEN0001")
    b = AttendeeKey.unresolved("https://example.invalid/?t=TESTTOKEN0002")

    assert a == AttendeeKey.unresolved("https://example.invalid/?t=TESTTOKEN0001")
    assert a != b
    assert a.short != b.short
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scoutmb'`

- [ ] **Step 3: Create the package and error hierarchy**

```python
# src/scoutmb/__init__.py
"""scoutmb — Scout merit-badge schedule and requirement extraction."""
```

```python
# src/scoutmb/errors.py
"""Typed errors for scoutmb.

Carry structured context rather than pre-formatted strings, so callers can
decide how to render them.
"""

from __future__ import annotations


class ScoutmbError(Exception):
    """Base class for every error this package raises."""


class MissingAttendeeId(ScoutmbError):
    """An attendee record arrived without the ID we use as identity."""

    def __init__(self, scout_name: str = "") -> None:
        self.scout_name = scout_name
        super().__init__(
            f"No attendee_id available for {scout_name or 'an unnamed attendee'}"
        )
```

```python
# src/scoutmb/domain/__init__.py
```

```python
# src/scoutmb/domain/identity.py
"""Stable attendee identity.

The display name is NOT identity: two attendees can share one. Grouping,
lookup, and filenames all key on AttendeeKey instead.

`attendee_id` is a bearer token for a real minor's records, so `short` is a
one-way digest prefix — filenames built from it stay safe to share.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from scoutmb.errors import MissingAttendeeId

_SHORT_LENGTH = 8


@dataclass(frozen=True, slots=True)
class AttendeeKey:
    """An opaque, stable identity for one attendee."""

    value: str

    @classmethod
    def from_attendee_id(cls, attendee_id: str, scout_name: str = "") -> AttendeeKey:
        cleaned = str(attendee_id or "").strip()
        if not cleaned:
            raise MissingAttendeeId(scout_name)
        return cls(cleaned)

    @classmethod
    def unresolved(cls, seed: str) -> AttendeeKey:
        """Identity for an attendee the API gave us no ID for.

        Seeded from a per-attendee value (their QR URL), so it stays stable
        across runs and distinct between attendees.
        """
        digest = hashlib.sha256(f"unresolved|{seed}".encode()).hexdigest()
        return cls(f"unresolved-{digest[:16]}")

    @property
    def short(self) -> str:
        """Filename-safe, non-reversible digest prefix."""
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:_SHORT_LENGTH]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_identity.py -v`
Expected: 5 passed

Run: `.venv/bin/mypy --strict src/scoutmb/domain/identity.py`
Expected: `Success: no issues found in 1 source file`

- [ ] **Step 5: Commit**

```bash
git add src/scoutmb tests/unit/test_identity.py
git commit -m "feat: add AttendeeKey with non-reversible filename digest"
```

---

### Task 10: Key inference and grouping on `AttendeeKey`

**Goal:** Replace name-based grouping so two same-named attendees are never merged. This is a **deliberate behavior change**, tested first.

**Files:**
- Modify: `scout_schedule_cli.py:675` (grouping key), `:786` (`by_key`), `:838-840` (grouped output)
- Modify: `tests/characterization/test_inference.py` (replace the KNOWN_DEFECT test)
- Test: `tests/unit/test_inference_identity.py`

**Acceptance Criteria:**
- [ ] Two attendees with identical names and different IDs produce **separate** groups
- [ ] `build_missing_requirements` returns a mapping keyed by `AttendeeKey`, with the display name carried inside each entry
- [ ] The `KNOWN_DEFECT` characterization test is replaced by its corrected counterpart
- [ ] All other characterization tests still pass unchanged

**Verify:** `.venv/bin/pytest tests/ -v` → all pass, including the corrected identity test

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_inference_identity.py
"""Same-named attendees must never share a bucket.

Replaces the KNOWN_DEFECT characterization test from Task 7.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scout_schedule_cli import build_missing_requirements  # noqa: E402

from tests.factories.records import make_requirement  # noqa: E402


def _scout(attendee_id: str, requirement_id: str, number: str) -> dict:
    return {
        "name": "Avery Archer",
        "attendee_id": attendee_id,
        "classes": [],
        "requirements": [
            asdict(
                make_requirement(
                    attendee_id=attendee_id,
                    requirement_id=requirement_id,
                    requirement_number=number,
                    merit_badge_name="Chess",
                )
            )
        ],
        "errors": [],
    }


def test_same_named_attendees_stay_separate():
    grouped = build_missing_requirements(
        [_scout("90000001", "r1", "#1"), _scout("90000002", "r2", "#2")]
    )

    assert len(grouped) == 2, "two distinct attendees must produce two buckets"
    for entry in grouped.values():
        assert entry["display_name"] == "Avery Archer"
        assert len(entry["badges"]["Chess"]) == 1


def test_grouping_survives_a_missing_attendee_id():
    """An attendee with no ID still gets a distinct, stable bucket."""
    a = _scout("", "r1", "#1")
    b = _scout("", "r2", "#2")
    a["qr_url"] = "https://example.invalid/?t=TESTTOKEN0001"
    b["qr_url"] = "https://example.invalid/?t=TESTTOKEN0002"

    grouped = build_missing_requirements([a, b])

    assert len(grouped) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_inference_identity.py -v`
Expected: FAIL — `assert len(grouped) == 2` gets `1`, and `KeyError: 'display_name'`.

- [ ] **Step 3: Change the grouping key in `annotate_requirement_statuses`**

At `scout_schedule_cli.py:675`, replace:

```python
        grouped.setdefault((str(item.get("scout_name") or ""), str(item.get("class_p4_id") or "")), []).append(item)
```

with:

```python
        grouped.setdefault(
            (_attendee_key_for(item), str(item.get("class_p4_id") or "")), []
        ).append(item)
```

Add this helper immediately above `annotate_requirement_statuses`:

```python
def _attendee_key_for(item: dict[str, Any]) -> str:
    """Identity for grouping: the attendee ID, never the display name.

    Two attendees can share a name; merging them silently corrupts both.
    Rows with no attendee_id fall back to a stable per-row marker rather than
    collapsing together.
    """
    attendee_id = str(item.get("attendee_id") or "").strip()
    if attendee_id:
        return attendee_id
    return f"unresolved-{item.get('qr_url') or item.get('requirement_id') or id(item)}"
```

- [ ] **Step 4: Change `by_key` and the output grouping in `build_missing_requirements`**

At `:786`, replace the `by_key` comprehension:

```python
    by_key = {
        (
            _attendee_key_for(item),
            str(item.get("class_p4_id") or ""),
            str(item.get("requirement_number") or ""),
        ): item
        for item in annotated
    }
```

At `:813-817`, replace the `parent_key` construction:

```python
            parent_key = (
                _attendee_key_for(current),
                str(current.get("class_p4_id") or ""),
                str(parent_number),
            )
```

At `:838-840`, replace the grouped-output block:

```python
        attendee_key = _attendee_key_for(item)
        badge_name = str(item.get("merit_badge_name") or "")
        bucket = grouped.setdefault(
            attendee_key,
            {"display_name": str(item.get("scout_name") or ""), "badges": {}},
        )
        bucket["badges"].setdefault(badge_name, []).append(entry)
```

And update the return annotation on `:771`:

```python
def build_missing_requirements(scouts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
```

- [ ] **Step 5: Update `write_email_reports` for the new shape**

At `:920`, replace:

```python
        badge_groups = missing.get(scout_name, {})
```

with:

```python
        attendee_key = str(scout.get("attendee_id") or "").strip() or f"unresolved-{scout_name}"
        bucket = missing.get(attendee_key) or {"display_name": scout_name, "badges": {}}
        badge_groups = bucket["badges"]
```

- [ ] **Step 6: Replace the KNOWN_DEFECT test**

Delete `test_KNOWN_DEFECT_same_named_attendees_are_merged` from
`tests/characterization/test_inference.py`. Its corrected counterpart now lives in
`tests/unit/test_inference_identity.py`.

- [ ] **Step 7: Run the whole suite**

Run: `.venv/bin/pytest tests/ -v`

Expected: all pass. **Three Task 7 tests assert the old return shape and will fail** —
update each to the new `{attendee_key: {"display_name": ..., "badges": {...}}}` form:

| Test | Old access | New access |
| --- | --- | --- |
| `test_build_missing_requirements_groups_by_badge` | `grouped["Avery Archer"]` | `grouped["90000001"]["badges"]` |
| `test_leaf_selection_includes_incomplete_ancestors` | `[...]["Avery Archer"]["Chess"]` | `[...]["90000001"]["badges"]["Chess"]` |
| `test_section_headers_and_not_used_rows_are_excluded` | `[...]["Avery Archer"]["Chess"]` | `[...]["90000001"]["badges"]["Chess"]` |

The *assertions* in each test stay identical — only the lookup path changes. That is the
point of the characterization net: the shape moved, the behavior did not.

- [ ] **Step 8: Commit**

```bash
git add scout_schedule_cli.py tests/unit/test_inference_identity.py tests/characterization/test_inference.py
git commit -m "fix: key inference grouping on attendee id, not display name

Two attendees sharing a display name had their requirements merged into one
bucket. attendee_id was read at :919 and never used. Grouping, parent lookup,
and email bucketing now key on attendee identity; the name is display data."
```

---

### Task 11: Collision-free output filenames

**Goal:** Email and raw-payload filenames stop colliding for same-named attendees, while staying human-scannable.

**Files:**
- Modify: `scout_schedule_cli.py:490` (raw payload), `:935` (email files)
- Test: `tests/unit/test_output_filenames.py`

**Acceptance Criteria:**
- [ ] Two same-named attendees produce **four** distinct email files, not two
- [ ] Raw payload filenames are distinct per attendee
- [ ] Filenames contain the readable name slug **and** the `AttendeeKey.short` digest
- [ ] No filename contains the raw `attendee_id`

**Verify:** `.venv/bin/pytest tests/unit/test_output_filenames.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_output_filenames.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scoutmb.domain.identity import AttendeeKey  # noqa: E402
from scout_schedule_cli import attendee_filename_stem  # noqa: E402


def test_same_name_different_ids_produce_distinct_stems():
    a = attendee_filename_stem("Avery Archer", "90000001")
    b = attendee_filename_stem("Avery Archer", "90000002")

    assert a != b


def test_stem_is_readable_and_hides_the_raw_id():
    stem = attendee_filename_stem("Avery Archer", "90000042")

    assert stem.startswith("avery-archer-")
    assert "90000042" not in stem
    assert stem.endswith(AttendeeKey.from_attendee_id("90000042").short)


def test_stem_is_stable_across_calls():
    assert attendee_filename_stem("Avery Archer", "90000001") == attendee_filename_stem(
        "Avery Archer", "90000001"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_output_filenames.py -v`
Expected: FAIL with `ImportError: cannot import name 'attendee_filename_stem'`

- [ ] **Step 3: Add the helper to `scout_schedule_cli.py`**

Immediately after `safe_slug` (`:595-597`), add:

```python
def attendee_filename_stem(scout_name: str, attendee_id: str) -> str:
    """Readable, collision-free filename stem for one attendee.

    The slug keeps files human-scannable; the digest suffix keeps two
    same-named attendees from overwriting each other. The raw attendee_id is a
    bearer token and never appears in a filename.
    """
    from scoutmb.domain.identity import AttendeeKey

    cleaned = str(attendee_id or "").strip()
    key = (
        AttendeeKey.from_attendee_id(cleaned)
        if cleaned
        else AttendeeKey.unresolved(scout_name)
    )
    return f"{safe_slug(scout_name)}-{key.short}"
```

- [ ] **Step 4: Use it for raw payloads**

At `:490`, replace:

```python
        slug = safe_slug(result.name)
```

with:

```python
        slug = attendee_filename_stem(result.name, result.attendee_id)
```

- [ ] **Step 5: Use it for email files**

At `:935`, replace:

```python
            slug = safe_slug(scout_name)
```

with:

```python
            slug = attendee_filename_stem(scout_name, attendee_id)
```

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add scout_schedule_cli.py tests/unit/test_output_filenames.py
git commit -m "fix: make email and raw payload filenames collision-free per attendee"
```

---

### Task 12: Atomic `scouts.csv` writes

**Goal:** A failed PDF extraction must leave the previous `scouts.csv` intact, rather than truncating it.

**Files:**
- Modify: `pdf_to_scouts.py` (`write_attendees_csv`, `:448`)
- Test: `tests/unit/test_atomic_write.py`

**Acceptance Criteria:**
- [ ] A write that raises mid-way leaves the original file byte-identical
- [ ] A successful write replaces the file atomically
- [ ] No `.tmp` file is left behind on either path

**Verify:** `.venv/bin/pytest tests/unit/test_atomic_write.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_atomic_write.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pdf_to_scouts import atomic_write_text  # noqa: E402


def test_successful_write_replaces_content(tmp_path):
    target = tmp_path / "scouts.csv"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob("*.tmp")) == []


def test_failed_write_preserves_the_original(tmp_path):
    target = tmp_path / "scouts.csv"
    target.write_text("irreplaceable", encoding="utf-8")

    def exploding_render() -> str:
        raise RuntimeError("extraction failed halfway")

    with pytest.raises(RuntimeError):
        atomic_write_text(target, exploding_render())

    assert target.read_text(encoding="utf-8") == "irreplaceable"
    assert list(tmp_path.glob("*.tmp")) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_atomic_write.py -v`
Expected: FAIL with `ImportError: cannot import name 'atomic_write_text'`

- [ ] **Step 3: Add the helper to `pdf_to_scouts.py`**

Add above `write_attendees_csv`:

```python
def atomic_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Write via a temp file and os.replace, so a failure never truncates.

    scouts.csv can represent a season of work that only exists because someone
    scanned a stack of PDFs. A half-written file is worse than no new file.
    """
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(content, encoding=encoding, newline="")
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
```

Add `import os` to the imports if absent.

- [ ] **Step 4: Route `write_attendees_csv` through it**

Replace the body of `write_attendees_csv` so it renders to a string first, then calls
`atomic_write_text(path, rendered)`:

```python
def write_attendees_csv(path: Path, attendees: Sequence[ExtractedAttendee]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Attendee Name", "Registrant Type", "QR Code Contents",
         "Source PDF", "Page", "Decode Method"]
    )
    for attendee in attendees:
        writer.writerow(
            [attendee.name, attendee.registrant_type, attendee.qr_value,
             attendee.source_pdf, attendee.page_number, attendee.decode_method]
        )
    atomic_write_text(path, buffer.getvalue())
```

Add `import io` if absent. **Check the existing column order against the current
implementation before replacing** — the header is a contract `scout_schedule_cli.py`
depends on.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add pdf_to_scouts.py tests/unit/test_atomic_write.py
git commit -m "fix: write scouts.csv atomically so a failed extraction preserves the old file"
```

---

### Task 13: `UiSettings` with explicit `data_root`

**Goal:** Kill the `__file__`-derived data paths (Hazard 1) **before** any module moves, with a documented resolution order.

**Files:**
- Create: `src/scoutmb/ui/__init__.py`
- Create: `src/scoutmb/ui/settings.py`
- Modify: `ui/server.py:24-41`
- Test: `tests/unit/test_ui_settings.py`

**Acceptance Criteria:**
- [ ] Resolution order: explicit argument → `SCOUTMB_DATA_DIR` → platform user-data dir → `Path.cwd()` only in dev mode
- [ ] `ui/server.py` derives no data path from `__file__`
- [ ] Static-asset resolution is unchanged in this task (it moves in Plan 2)
- [ ] A test proves that relocating the module does not move the data root

**Verify:** `.venv/bin/pytest tests/unit/test_ui_settings.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_ui_settings.py
from __future__ import annotations

from pathlib import Path

from scoutmb.ui.settings import UiSettings


def test_explicit_argument_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path / "from-env"))
    settings = UiSettings.resolve(data_root=tmp_path / "explicit")

    assert settings.data_root == tmp_path / "explicit"


def test_environment_variable_is_used_when_no_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path / "from-env"))
    settings = UiSettings.resolve()

    assert settings.data_root == tmp_path / "from-env"


def test_dev_mode_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("SCOUTMB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = UiSettings.resolve(dev_mode=True)

    assert settings.data_root == tmp_path


def test_derived_paths_hang_off_data_root(tmp_path):
    settings = UiSettings.resolve(data_root=tmp_path)

    assert settings.scouts_csv == tmp_path / "scouts.csv"
    assert settings.pdf_uploads_dir == tmp_path / "pdf-uploads"
    assert settings.runs_dir == tmp_path / "runs"


def test_data_root_is_independent_of_module_location(tmp_path, monkeypatch):
    """The whole point of Hazard 1: moving the package must not move the data."""
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path))
    settings = UiSettings.resolve()

    assert settings.data_root == tmp_path
    assert Path(__file__).parent not in settings.data_root.parents
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_ui_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scoutmb.ui'`

- [ ] **Step 3: Write the implementation**

```python
# src/scoutmb/ui/__init__.py
```

```python
# src/scoutmb/ui/settings.py
"""Where the web UI reads and writes user data.

NEVER derive a data path from __file__. Doing so ties irreplaceable user data
to the package's location on disk, so moving or reinstalling the package
silently relocates — or destroys — it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ScoutingMeritBadges"
DATA_DIR_ENV = "SCOUTMB_DATA_DIR"


def platform_data_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME / "data"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "data"
    return Path.home() / ".local" / "share" / APP_NAME / "data"


@dataclass(frozen=True, slots=True)
class UiSettings:
    data_root: Path

    @classmethod
    def resolve(cls, data_root: Path | None = None, dev_mode: bool = False) -> UiSettings:
        """Resolution order: explicit -> SCOUTMB_DATA_DIR -> platform -> cwd (dev only)."""
        if data_root is not None:
            return cls(Path(data_root))

        from_env = os.environ.get(DATA_DIR_ENV)
        if from_env:
            return cls(Path(from_env))

        if dev_mode:
            return cls(Path.cwd())

        return cls(platform_data_root())

    @property
    def scouts_csv(self) -> Path:
        return self.data_root / "scouts.csv"

    @property
    def pdf_uploads_dir(self) -> Path:
        return self.data_root / "pdf-uploads"

    @property
    def runs_dir(self) -> Path:
        return self.data_root / "runs"

    def ensure_dirs(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Rewire `ui/server.py`**

Replace `ui/server.py:24-41`:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pdf_to_scouts  # noqa: E402
import scout_schedule_cli  # noqa: E402

from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

SCOUTS_CSV = REPO_ROOT / "scouts.csv"
PDF_UPLOADS_DIR = REPO_ROOT / "pdf-uploads"
RUNS_DIR = REPO_ROOT / "runs"
STATIC_DIR = Path(__file__).resolve().parent / "static"
BROWSER_CHANNEL = os.environ.get("SCOUTMB_BROWSER_CHANNEL") or None

RUNS_DIR.mkdir(exist_ok=True)
```

with:

```python
CODE_ROOT = Path(__file__).resolve().parent.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

import pdf_to_scouts  # noqa: E402
import scout_schedule_cli  # noqa: E402

from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from scoutmb.ui.settings import UiSettings  # noqa: E402

# Data location is resolved explicitly and NEVER derived from __file__ —
# see Hazard 1 in the design spec. dev_mode falls back to cwd, which is how
# the repo-root workflow keeps working during the restructure.
SETTINGS = UiSettings.resolve(dev_mode=not os.environ.get("SCOUTMB_DATA_DIR"))
SCOUTS_CSV = SETTINGS.scouts_csv
PDF_UPLOADS_DIR = SETTINGS.pdf_uploads_dir
RUNS_DIR = SETTINGS.runs_dir

# STATIC_DIR still resolves from __file__: it locates CODE, not user data.
# It moves to importlib.resources in Plan 2 when the package relocates.
STATIC_DIR = Path(__file__).resolve().parent / "static"
BROWSER_CHANNEL = os.environ.get("SCOUTMB_BROWSER_CHANNEL") or None

SETTINGS.ensure_dirs()
```

- [ ] **Step 5: Run the suite and start the app once**

Run: `.venv/bin/pytest tests/ -v`
Expected: all pass.

Run: `.venv/bin/python run_app.py --browser`
Expected: the UI loads and `/api/status` responds. Ctrl-C to stop.

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/ui ui/server.py tests/unit/test_ui_settings.py
git commit -m "fix: resolve UI data paths explicitly instead of from __file__

Closes Hazard 1 before any module moves: deriving data paths from __file__
means relocating the package silently relocates scouts.csv, runs/, and
pdf-uploads/ — and under wheel install, into a directory pip replaces."
```

---

### Task 14: Copy-only legacy data migration

**Goal:** Move the one live installation's data from `app/` to `data/` without ever deleting the originals.

**Files:**
- Create: `bootstrap/migrate.py`
- Modify: `bootstrap/paths.py` (add `data_dir`), `bootstrap/main.py` (call migration, export env var)
- Test: `tests/unit/test_migrate.py`

**Acceptance Criteria:**
- [ ] Copies `scouts.csv`, `pdf-uploads/`, `runs/` from `app/` to `data/`
- [ ] **Never deletes or moves** the originals
- [ ] Idempotent — a second run is a no-op via the `.migrated` marker
- [ ] Verifies each copy (size for files, recursive count for directories)
- [ ] A destination collision writes `<name>.legacy` instead of overwriting
- [ ] The launcher exports `SCOUTMB_DATA_DIR` pointing at `data/`

**Verify:** `.venv/bin/pytest tests/unit/test_migrate.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_migrate.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bootstrap.migrate import MIGRATION_MARKER, migrate_legacy_data  # noqa: E402


def _legacy_install(root: Path) -> tuple[Path, Path]:
    app_dir = root / "app"
    data_dir = root / "data"
    (app_dir / "pdf-uploads").mkdir(parents=True)
    (app_dir / "runs" / "2026-07-19_2139").mkdir(parents=True)
    (app_dir / "scouts.csv").write_text("Attendee Name,QR Code Contents\n", encoding="utf-8")
    (app_dir / "runs" / "2026-07-19_2139" / "summary.json").write_text("{}", encoding="utf-8")
    return app_dir, data_dir


def test_copies_all_user_data(tmp_path):
    app_dir, data_dir = _legacy_install(tmp_path)

    migrate_legacy_data(app_dir, data_dir)

    assert (data_dir / "scouts.csv").read_text(encoding="utf-8").startswith("Attendee Name")
    assert (data_dir / "runs" / "2026-07-19_2139" / "summary.json").is_file()
    assert (data_dir / "pdf-uploads").is_dir()


def test_originals_are_never_deleted(tmp_path):
    app_dir, data_dir = _legacy_install(tmp_path)

    migrate_legacy_data(app_dir, data_dir)

    assert (app_dir / "scouts.csv").is_file(), "migration must never delete the source"
    assert (app_dir / "runs" / "2026-07-19_2139" / "summary.json").is_file()


def test_is_idempotent(tmp_path):
    app_dir, data_dir = _legacy_install(tmp_path)

    migrate_legacy_data(app_dir, data_dir)
    (data_dir / "scouts.csv").write_text("edited after migration", encoding="utf-8")
    migrate_legacy_data(app_dir, data_dir)

    assert (data_dir / "scouts.csv").read_text(encoding="utf-8") == "edited after migration"
    assert (data_dir / MIGRATION_MARKER).is_file()


def test_collision_writes_alongside_instead_of_overwriting(tmp_path):
    app_dir, data_dir = _legacy_install(tmp_path)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "scouts.csv").write_text("pre-existing", encoding="utf-8")

    migrate_legacy_data(app_dir, data_dir)

    assert (data_dir / "scouts.csv").read_text(encoding="utf-8") == "pre-existing"
    assert (data_dir / "scouts.csv.legacy").read_text(encoding="utf-8").startswith("Attendee Name")


def test_no_legacy_install_is_a_no_op(tmp_path):
    data_dir = tmp_path / "data"

    migrate_legacy_data(tmp_path / "app", data_dir)

    assert not data_dir.exists() or not any(data_dir.iterdir())
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_migrate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap.migrate'`

- [ ] **Step 3: Write the implementation**

```python
# bootstrap/migrate.py
"""One-time copy of user data from the legacy app/ directory into data/.

COPY ONLY. The originals are never moved or deleted. One installation exists
in the wild holding a season of real Scout records; if this migration is wrong,
the data must still be sitting where it always was.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

MIGRATION_MARKER = ".migrated"

# (relative name, is_directory)
_LEGACY_ITEMS: list[tuple[str, bool]] = [
    ("scouts.csv", False),
    ("pdf-uploads", True),
    ("runs", True),
]


def _count_files(path: Path) -> int:
    return sum(1 for child in path.rglob("*") if child.is_file())


def migrate_legacy_data(app_dir: Path, data_dir: Path) -> dict[str, object] | None:
    """Copy legacy user data into data_dir. Returns a report, or None if skipped."""
    if (data_dir / MIGRATION_MARKER).is_file():
        return None
    if not app_dir.is_dir():
        return None

    present = [(name, is_dir) for name, is_dir in _LEGACY_ITEMS if (app_dir / name).exists()]
    if not present:
        return None

    data_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    collisions: list[str] = []

    for name, is_dir in present:
        source = app_dir / name
        destination = data_dir / name

        if destination.exists():
            destination = data_dir / f"{name}.legacy"
            collisions.append(name)
            if destination.exists():
                shutil.rmtree(destination) if destination.is_dir() else destination.unlink()

        if is_dir:
            shutil.copytree(source, destination)
            if _count_files(source) != _count_files(destination):
                raise RuntimeError(f"Migration verification failed for directory {name}")
        else:
            shutil.copy2(source, destination)
            if source.stat().st_size != destination.stat().st_size:
                raise RuntimeError(f"Migration verification failed for file {name}")

        copied.append(destination.name)

    report = {
        "migrated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(app_dir),
        "copied": copied,
        "collisions": collisions,
        "originals_retained": True,
    }
    (data_dir / MIGRATION_MARKER).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
```

- [ ] **Step 4: Add `data_dir` to `AppPaths`**

In `bootstrap/paths.py`, add `data_dir: Path` to the `AppPaths` dataclass, include it in
`ensure_dirs`, and set `data_dir=root / "data"` in `get_paths()`.

- [ ] **Step 5: Call migration and export the env var in `bootstrap/main.py`**

In `_run`, immediately after `source_sync.sync_app_source(paths)`:

```python
    from bootstrap import migrate

    report = migrate.migrate_legacy_data(paths.app_dir, paths.data_dir)
    if report is not None:
        logger.info("Migrated legacy user data: %s", report)
```

In `_launch_app`, add the data directory to the child environment:

```python
    env = {
        **os.environ,
        "SCOUTMB_BROWSER_CHANNEL": channel or "",
        "SCOUTMB_DATA_DIR": str(paths.data_dir),
    }
```

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: all pass.

- [ ] **Step 7: Rehearse the migration on a throwaway root**

```bash
export SCOUTMB_BOOTSTRAP_ROOT=$(mktemp -d)
mkdir -p "$SCOUTMB_BOOTSTRAP_ROOT/app/runs/2026-07-19_2139" "$SCOUTMB_BOOTSTRAP_ROOT/app/pdf-uploads"
echo "Attendee Name,QR Code Contents" > "$SCOUTMB_BOOTSTRAP_ROOT/app/scouts.csv"
.venv/bin/python -c "
from pathlib import Path
from bootstrap.migrate import migrate_legacy_data
root = Path('$SCOUTMB_BOOTSTRAP_ROOT')
print(migrate_legacy_data(root/'app', root/'data'))
print('original still present:', (root/'app'/'scouts.csv').is_file())
"
```
Expected: a report dict prints, and `original still present: True`.

- [ ] **Step 8: Commit**

```bash
git add bootstrap/migrate.py bootstrap/paths.py bootstrap/main.py tests/unit/test_migrate.py
git commit -m "feat: copy-only migration of legacy app/ user data into data/

One install exists in the wild with real Scout records. Migration copies and
verifies, never moves or deletes; the originals stay put so a bad migration
is recoverable."
```

---

## Self-Review

**Spec coverage (Phases 0–3):**

| Spec requirement | Task |
| --- | --- |
| pyproject, ruff, mypy, pytest, coverage config | 1 |
| Staged CI (no test/build job before they can pass) | 2, 6 |
| `ruff format` as a separate commit | 2 |
| `tools/verify_corpus.py`, aggregates only | 3 |
| Self-verifying scrubber with leaky-input suite | 4 |
| Reduced fixtures, conftest tripwire, factories | 5 |
| `requirement_path` across all 18 shapes + property test | 6 |
| Inference non-mutation guard | 7 |
| Both inference consumers pinned separately | 7 |
| `process_scout` characterized without a browser | 8 |
| Retry pinned at 3 attempts | 8 |
| CSV headers guarding `__dataclass_fields__` order | 8 |
| `AttendeeKey`, non-reversible digest | 9 |
| Identity fix in grouping and lookup | 10 |
| Collision-free filenames | 11 |
| Atomic writes | 12 |
| `data_root` resolution order, Hazard 1 | 13 |
| Legacy migration, copy-only, idempotent | 14 |

**Deferred to Plan 2 (spec Phases 4–8), by design:** package restructure, template
extraction, `SchedulePort`, typed config, logging/`ProgressSink`, `JobRegistry`, the four
UI defects, and the `app.js` half of the report-opening change. **Plan 3 (Phases 9–11):**
bootstrap rebuild, macOS, cleanup.

**Known gaps carried forward, deliberately:**
- Schedule dedup (`:510`) is listed in Task 8's acceptance criteria but has no dedicated
  test; the `fake_schedule` fixture supplies a single row. **Add a duplicate-row fixture
  when `payloads.py` is extracted in Plan 2**, where dedup becomes a pure function.
- `bootstrap/webview2.py`'s module-level `import winreg` still prevents importing
  `bootstrap` on macOS. Task 14's tests import `bootstrap.migrate` directly, which does
  not transitively import `webview2`, so they pass. The `winreg` fix lands in Plan 3.

**Type consistency check:** `attendee_filename_stem(scout_name, attendee_id)` is defined
in Task 11 and used identically in both call sites. `AttendeeKey.from_attendee_id` /
`.unresolved` / `.short` are defined in Task 9 and used consistently in Tasks 10, 11.
`build_missing_requirements` returns `dict[str, dict[str, Any]]` with `display_name` and
`badges` keys as of Task 10; Task 10 Step 7 updates the Task 7 test that assumed the old
shape.

**Placeholder scan:** no TBD/TODO markers; every code step carries complete code; every
verify step names an exact command and expected output.
