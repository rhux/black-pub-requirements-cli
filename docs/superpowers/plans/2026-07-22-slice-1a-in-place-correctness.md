# Slice 1a — Foundation & In-Place Correctness (READY)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:executing-plans (or subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The `.tasks.json` sidecar is the machine-readable source; each task's `description` mirrors the Goal/Files/Acceptance/Verify below with a `json:metadata` fence.

**Status:** READY — execute this slice now.
**Spec:** `docs/superpowers/specs/2026-07-21-scoutmb-refactor-design.md`
**Slice:** 1a of a 5-part set. Companion: **`2026-07-22-slice-1b-full-phase-a-characterization.md`**
(the exhaustive Phase A characterization matrix, the parity oracle for Slice 2). Slices 2–4
are PRELIMINARY, refined after **Gate 1b** (in 1b) passes.

**Why split from 1b:** three review passes showed a single "full characterization + all
in-place fixes" slice was too large to get right incrementally. 1a is the finishable unit
that ships the live-install protection and the data-merge fix; 1b holds the exhaustive
behavior matrix that becomes Slice 2's parity oracle. Each in-place fix here **self-guards**
(pins exactly the behavior it changes), so 1a does not depend on 1b's matrix; 1b is additive
breadth. Sequencing: **1a → 1b → Slice 2** (1b may run in parallel with 1a since it is
read-only characterization, but Gate 1b precedes Slice 2).

**Goal:** Stand up Python 3.12 tooling, an offline-enforced test suite, targeted
characterization that guards each fix, and the surgical in-place correctness fixes that
protect the one live install — attendee identity, atomic writes, explicit data root,
copy-only migration — all **before** any package restructure (Slice 2).

**Architecture:** No hexagonal restructure yet. The flat modules stay; the fix helpers are
defined **in the flat scripts the launcher ships** (not `src/scoutmb`, which the launcher
does not sync). `src/scoutmb` holds only test/offline-guard support. `uv` is the toolchain;
`uv.lock` is canonical.

**Tech stack:** Python 3.12 (dev machine is 3.14 — install 3.12 via `uv python install`),
uv, ruff, mypy, pytest + pytest-cov + pytest-socket + hypothesis, PyMuPDF, OpenCV,
Playwright, FastAPI.

**User decisions (already made):**
- North star is extensibility + best practices; ship the live-bug fix and data protection first.
- Package name `scoutmb`; console command `troop349`.
- Internal identity keys on the upstream attendee ID (fail closed if blank); **output**
  identity is a full per-run UUIDv4 — raw attendee ID and QR tokens never appear in
  shareable artifacts, filenames, or logs.
- Committed fixtures are fully synthetic; `raw_data/` stays local, gitignored, aggregates-only.
- One live install exists; migration is copy-only and never deletes originals.

---

## Execution rules

1. Run a task only when its `blockedBy` tasks are complete.
2. Write the named RED test before changing production behavior. Characterization tests
   may start green **only** when they pin existing behavior — mark those explicitly.
3. Run each task's Verify command; the task is done only when the expected output is seen.
4. Never commit `raw_data/`, generated private reports, or unrelated changes.
5. Run the PII sweep (Task 5) before committing anything that touches `tests/`.
6. **Characterization imports the legacy module, which imports Playwright + openpyxl at
   module scope (`scout_schedule_cli.py:27-28`).** Any task that imports
   `scout_schedule_cli` (Tasks 4, 7, 8, 9, 11, 12) must run after
   `uv sync --locked --all-extras`, not the bare `uv sync --locked`. Making those imports
   lazy is a Slice-2 change; Slice 1 characterizes the module as-is, with its real deps
   installed.
7. **Leave every task's new files lint-clean.** Before each commit run
   `uv run ruff check --fix <new files>` and `uv run ruff format <new files>` scoped to the
   files that task created — never `git add -A` and never a repo-wide format after Task 2.
   Gate 1 runs `ruff format --check .` and will fail on any unformatted snippet.
8. **`raw_data/` is a local-only, developer-run corpus.** Commands that pass `--corpus
   raw_data` (Tasks 5, 6, Gate 1) run on the developer's machine where the gitignored corpus
   exists; in CI the corpus is absent and those checks degrade to pattern-only (the conftest
   and tools handle this). This is a private-corpus augmentation, not a hosted-CI gate.

## Scope honesty (narrowed after a /codex review)

Slice 1 makes **in-place, characterization-guarded** fixes before any restructure. It does
**not** fully discharge every KEEP decision — those complete in later slices:

- **Identity (D3/D14/D25):** Slice 1 fixes *grouping* (Task 11) and *output filenames*
  (Task 12) only. The raw `attendee_id`/QR tokens still appear in `scouts.json`, the CSVs,
  and the email CSV; **replacing those columns with the per-run UUID is Slice 2**, where
  outputs move behind versioned schemas.
- **Atomic writes (D11):** Slice 1 gives the user-facing writers (`scouts.csv`, report,
  emails) temp+fsync+`os.replace`. **Exclusive same-dir temp, parent-directory fsync, a
  documented post-replace durability result, and routing *every* JSON/CSV/raw artifact are
  Slice 2.**
- **Migration (D5):** Slice 1 does copy-only migration **with per-file SHA-256
  verification**. Staging, resumability, and the marker-ordering contract are Slice 3.

## Prerequisite: a 3.12 interpreter

The dev venv is 3.14; the shipped runtime is 3.12 and CI is the authority. Before Task 1:

```bash
uv python install 3.12
```

## File structure created by this slice

| File | Responsibility |
| --- | --- |
| `pyproject.toml`, `.python-version`, `uv.lock` | Project metadata, pinned 3.12, canonical lock |
| `.github/workflows/ci.yml` | Staged CI (lint, types, lock; test job added in Task 7) |
| `tests/conftest.py` | Offline enforcement + fixture tripwire |
| `src/scoutmb/network_policy.py` | Application-level egress guard |
| `tools/verify_corpus.py`, `tools/check_private_data.py` | Local aggregate corpus check; PII scanner |
| `tests/factories/`, `tests/fakes/` | Deterministic synthetic test data + shared fakes |
| `tests/characterization/` | Pins legacy behavior of the flat modules |
| `src/scoutmb/errors.py`, `src/scoutmb/network_policy.py` | Test/offline-guard support (dev-installed; **not** shipped by the launcher) |
| `scout_schedule_cli.py` (in-place) | Gains `AttendeeId`/`RunIdentity`/`attendee_filename_stem`/`atomic_write_text` — the fix helpers live in the shipped flat script |
| `pdf_to_scouts.py` (in-place) | Gains its own `atomic_write_text` |
| `ui/server.py` (in-place) | Gains `UiSettings` (stdlib OS-dir resolution, no new dep) |
| `bootstrap/migrate.py` | Copy-only + SHA-256 legacy migration |

**Why helpers live in the flat scripts, not `src/scoutmb`:** the launcher's `source_sync.py`
ships the flat scripts and `ui/`, **not** `src/scoutmb`. Slice 1 is in-place fixes before the
restructure, so the fix code must live where it already ships. `src/scoutmb` in Slice 1 holds
only test/offline-guard support (imported by tests, which run in the dev env where the package
is `uv sync`-installed). Slice 2 relocates the helpers into `scoutmb` *with* launcher wiring.

---

### Task 1: Project tooling scaffold (uv, ruff, mypy, pytest, 3.12)

**Goal:** A Hatchling `src/` project pinned to Python 3.12 that syncs reproducibly from
`uv.lock`, with ruff/mypy/pytest/coverage configured. Zero production-source changes.

**Files:**
- Create: `pyproject.toml`, `.python-version`
- Generate: `uv.lock`
- Modify: `.gitignore`

**Acceptance Criteria:**
- [ ] `.python-version` is `3.12`; `requires-python = ">=3.12"`; ruff `target-version = "py312"`
- [ ] `src/scoutmb/__init__.py` and `tools/__init__.py` exist so `uv sync` can build the
      package and `mypy files=["src","tools"]` has real paths to check
- [ ] `uv sync --locked` succeeds and `uv run python -c "import scoutmb, sys;assert sys.version_info[:2]==(3,12)"` passes
- [ ] `uv run ruff check .` and `uv run mypy` exit 0 (nothing strictly typed yet)
- [ ] No test job in CI yet (Task 7 adds it)

**Verify:** `uv sync --locked && uv run ruff check . && uv run mypy && uv run python -c "import scoutmb, sys;assert sys.version_info[:2]==(3,12);print('py312 ok')"`

**Steps:**

- [ ] **Step 1: Pin the interpreter and create the package skeleton**

```bash
uv python pin 3.12
mkdir -p src/scoutmb tools
printf '"""scoutmb — Scout merit-badge schedule and requirement extraction."""\n' > src/scoutmb/__init__.py
printf '"""Developer tools (corpus verification, privacy scanning, baselines)."""\n' > tools/__init__.py
```

> `src/scoutmb/__init__.py` must exist now: `[tool.hatch.build.targets.wheel] packages =
> ["src/scoutmb"]` and `[tool.mypy] files = ["src","tools"]` both fail if the directories
> are missing. Task 3 adds modules alongside this `__init__.py`; it does not recreate it.

- [ ] **Step 2: Write `pyproject.toml`**

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
    "openpyxl>=3.1,<4",
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.32,<1",
    "python-multipart>=0.0.12,<1",
    "pywebview>=5.3,<6",
]

[project.optional-dependencies]
acquisition = ["playwright>=1.57,<2"]
pdf = ["PyMuPDF>=1.24,<2", "opencv-python-headless>=4.10,<5"]

[project.scripts]
troop349 = "scoutmb.cli.app:main"

[dependency-groups]
dev = [
    "pytest>=8.3,<9",
    "pytest-cov>=6.0,<7",
    "pytest-asyncio>=0.24,<1",
    "pytest-socket>=0.7,<1",
    "hypothesis>=6.112,<7",
    "httpx>=0.27,<1",          # Starlette TestClient (used in Slice 1b) needs it
    "ruff>=0.8,<1",
    "mypy>=1.13,<2",
    "pyyaml>=6,<7",
]

[tool.hatch.build.targets.wheel]
packages = ["src/scoutmb"]

[tool.hatch.build]
exclude = ["bootstrap", "raw_data", "docs", "tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests", "tools"]
# The legacy flat scripts are characterized in Slice 1 and moved/rewritten in Slice 2; the
# bootstrap package is stdlib-only legacy rewritten in Slice 3/4. Excluding both keeps ruff
# from reformatting code about to move, preserves the line numbers this plan references, and
# avoids failing on pre-existing PTH violations (open()/os.replace in bootstrap). They
# re-enter ruff in their owning slice. New Slice-1 code (src/scoutmb, tools, tests) is linted.
extend-exclude = [
    "scout_schedule_cli.py", "pdf_to_scouts.py", "ui/server.py", "run_app.py", "bootstrap",
]
exclude = [".venv", "raw_data"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM", "PTH", "RET", "ARG", "TID"]
ignore = ["E501", "B008"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ARG"]

[tool.mypy]
python_version = "3.12"
files = ["src", "tools"]
ignore_missing_imports = true
warn_unused_ignores = true

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live_service: test may contact the real scoutingevent.com (deselected by default)",
    "playwright: test needs a real browser (deselected by default)",
]
addopts = "-m 'not live_service and not playwright' --strict-markers --strict-config"
asyncio_mode = "auto"
xfail_strict = true

[tool.coverage.run]
branch = true
source = ["src/scoutmb", "tools"]
```

- [ ] **Step 3: Extend `.gitignore`** (append; `/raw_data` and `.DS_Store` already present)

```gitignore
.pytest_cache/
.ruff_cache/
.mypy_cache/
htmlcov/
.coverage
dist/
build/
*.egg-info/
```

- [ ] **Step 4: Lock and sync**

```bash
uv lock
uv sync --locked
```

- [ ] **Step 5: Verify**

```bash
uv run ruff check . && uv run mypy && uv run python -c "import scoutmb, sys;assert sys.version_info[:2]==(3,12);print('py312 ok')"
```
Expected: `All checks passed!`, `Success: no issues found`, `py312 ok`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version uv.lock .gitignore src/scoutmb/__init__.py tools/__init__.py
git commit -m "build: uv/ruff/mypy/pytest scaffold pinned to Python 3.12"
```

---

### Task 2: Staged CI — lint, types, lock

**Goal:** A CI workflow that passes today: lint, types, and lock-drift only. No test or
build job yet (pytest with zero tests exits non-zero; `src/scoutmb` barely exists).

**Files:**
- Create: `.github/workflows/ci.yml`

**Acceptance Criteria:**
- [ ] Valid YAML; jobs `lint`, `types`, `lock` only; Python 3.12
- [ ] `lock` job fails if `uv.lock` is out of date
- [ ] `ruff format --check .` passes (the excluded legacy scripts are not touched)

**Verify:** `uv run python -c "import yaml,pathlib;yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text());print('valid')" && uv run ruff format --check .`

**Steps:**

- [ ] **Step 1: Write the workflow**

```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request:
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .
  types:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      - run: uv sync --locked
      - run: uv run mypy
  lock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv lock --check
```

- [ ] **Step 2: Verify YAML**

```bash
uv run python -c "import yaml,pathlib;yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text());print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Ensure the tracked files format-clean, scoped (no `git add -A`)**

The legacy flat scripts are excluded from ruff (Task 1), so `ruff format` only touches
`src`/`tools`/`tests`. Format just what exists, then confirm the check passes:

```bash
uv run ruff format src tools
uv run ruff format --check .
```
Expected: `--check` reports all files already formatted (nothing to commit if already clean).
Per-task formatting (execution rule 7) keeps every later task clean; there is no repo-wide
format commit.

- [ ] **Step 4: Commit the workflow**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint, types, and lock jobs on Python 3.12"
```

---

### Task 3: Offline test enforcement

**Goal:** Default tests cannot reach a non-loopback address. Python sockets are blocked,
an application-level network policy exists, and `scoutingevent.com` needs a two-part
opt-in (`live_service` marker + env var).

**Files:**
- Create: `src/scoutmb/network_policy.py`, `src/scoutmb/errors.py`
- Create: `tests/conftest.py` (network half; fixture-tripwire half added in Task 5)
- Create: `tests/network/test_offline_policy.py`

(`src/scoutmb/__init__.py` already exists from Task 1 — do not recreate it.)

**Acceptance Criteria:**
- [ ] A default test that **connects** to a non-loopback host fails
- [ ] Creating/binding a loopback socket is allowed (so FastAPI `TestClient` and local fakes work)
- [ ] `network_policy.assert_egress_allowed(host)` raises `ExternalNetworkBlocked` for a
      real host unless the two-part opt-in (`SCOUTMB_ALLOW_LIVE_SERVICE`) is set
- [ ] `uv run pytest -m "not live_service" -q` passes with zero real network use

**Verify:** `uv run pytest tests/network -q`

**Steps:**

- [ ] **Step 1: Write the RED tests**

```python
# tests/network/test_offline_policy.py
import socket
import pytest
from scoutmb.network_policy import ExternalNetworkBlocked, assert_egress_allowed


def test_non_loopback_socket_is_blocked():
    with pytest.raises(Exception):
        socket.create_connection(("93.184.216.34", 80), timeout=1)  # example.com IP


def test_loopback_is_allowed():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))  # binding loopback must not be blocked
    s.close()


def test_live_gateway_requires_two_part_opt_in(monkeypatch):
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    with pytest.raises(ExternalNetworkBlocked):
        assert_egress_allowed("scoutingevent.com")


def test_opt_in_allows_the_real_host(monkeypatch):
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    assert_egress_allowed("scoutingevent.com") is None
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/network -q
```
Expected: import error / failures (module + conftest missing).

- [ ] **Step 3: Implement the policy** (`src/scoutmb/__init__.py` already exists from Task 1)

```python
# src/scoutmb/network_policy.py
"""Application-level egress guard.

pytest-socket blocks Python sockets in tests, but a Playwright browser subprocess
is a separate process it cannot see. Feature code that is about to reach the network
calls assert_egress_allowed so the intent is guarded in the application too, not only
in the test harness.
"""

from __future__ import annotations

import os

from scoutmb.errors import ExternalNetworkBlocked

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_LIVE_OPT_IN = "SCOUTMB_ALLOW_LIVE_SERVICE"


def assert_egress_allowed(host: str) -> None:
    """Raise unless `host` is loopback or the two-part live opt-in is set."""
    if host in _LOOPBACK:
        return
    if os.environ.get(_LIVE_OPT_IN):
        return
    raise ExternalNetworkBlocked(host)
```

Add to `src/scoutmb/errors.py` (created here, extended in Task 10):

```python
# src/scoutmb/errors.py
"""Typed errors for scoutmb."""

from __future__ import annotations


class ScoutmbError(Exception):
    """Base class for every error this package raises."""


class ExternalNetworkBlocked(ScoutmbError):
    def __init__(self, host: str) -> None:
        self.host = host
        super().__init__(
            f"Egress to {host!r} is blocked. Set SCOUTMB_ALLOW_LIVE_SERVICE and use the "
            f"'live_service' marker to opt in."
        )
```

- [ ] **Step 4: Write `tests/conftest.py` (network half)**

```python
# tests/conftest.py
"""Offline enforcement. The fixture-safety tripwire is added in Task 5.

Uses pytest-socket in *host-restriction* mode, NOT full disable_socket: connections to
any host other than loopback raise, while socket creation and loopback bind stay allowed.
That keeps FastAPI TestClient (in-process ASGI) and local fake services working while
still blocking real egress. Full disable_socket would break the loopback-bind test and can
break asyncio loop internals on Windows.
"""

from __future__ import annotations

import pytest_socket


def pytest_runtest_setup(item):
    if item.get_closest_marker("live_service"):
        pytest_socket.enable_socket()  # opt-in tests may reach the real service
        return
    # connect() to anything but loopback raises SocketConnectBlockedError;
    # creation/bind are untouched, so loopback servers and TestClient still work.
    pytest_socket.socket_allow_hosts(["127.0.0.1", "::1"], allow_unix_socket=True)
```

> `socket_allow_hosts` guards `connect`; it does not replace `socket.socket`, so
> `socket.socket(AF_INET); bind(("127.0.0.1", 0))` in the loopback test succeeds while
> `create_connection(("93.184.216.34", 80))` raises. Do **not** also call `disable_socket` —
> that would block the loopback test and asyncio socketpairs.

- [ ] **Step 5: Run GREEN**

```bash
uv run pytest tests/network -q
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/scoutmb/network_policy.py src/scoutmb/errors.py tests/conftest.py tests/network/test_offline_policy.py
git commit -m "test: enforce offline-by-default with loopback allowance and live opt-in"
```

---

### Task 4: Synthetic factories and fixtures

**Goal:** Deterministic, fully synthetic builders for records and API payloads covering
the observed edge cases (18 requirement-number shapes, 5 flag combos, empty rows, label
rows, choice thresholds, same-name attendees). No committed fixture derives from real data.

**Files:**
- Create: `tests/factories/__init__.py`, `tests/factories/records.py`, `tests/factories/payloads.py`

**Acceptance Criteria:**
- [ ] `make_requirement`/`make_class` return valid records; tests override only the field under test
- [ ] `schedule_payload`/`requirement_payload` mirror the real API field names read by
      `process_scout` (`classP4ID`, `CLASS_NAME_ONLY`, `HAS_REQ`, `MDM_LKP_BADGE_REQ_ID`,
      `REQ_NBR_WEB_DISPLAY`, `COMPLETED_REQ_FLAG`, …)
- [ ] `REQUIREMENT_NUMBER_SHAPES` lists all 18 observed shapes

> **Note:** `records.py` imports `scout_schedule_cli` for `ClassRecord`/`RequirementRecord`,
> which imports Playwright + openpyxl at module scope. So this task's verify (and every later
> task that touches the factories or the legacy module) runs after
> `uv sync --locked --all-extras`, per execution rule 6. There is **no** "core-only import"
> claim in Slice 1 — that becomes true only after the Slice-2 lazy-import refactor.

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/factories -q`

**Steps:**

- [ ] **Step 1: `tests/factories/records.py`**

```python
# tests/factories/records.py
"""Builders for legacy record dataclasses. Defaults valid; override per test."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scout_schedule_cli import ClassRecord, RequirementRecord  # noqa: E402


def make_requirement(**overrides: Any) -> RequirementRecord:
    defaults: dict[str, Any] = {
        "scout_name": "Avery Archer", "attendee_id": "90000001",
        "class_number": "26MB1", "class_p4_id": "2000001",
        "merit_badge_name": "Chess", "requirement_id": "1001",
        "requirement_type_id": "1", "requirement_number": "#1",
        "description": "Discuss the history of chess.",
        "completed_requirement": False, "completed_class": False,
        "requirement_on_event": True, "present_days": "MoTuWeTh",
    }
    return RequirementRecord(**{**defaults, **overrides})


def make_class(**overrides: Any) -> ClassRecord:
    defaults: dict[str, Any] = {
        "scout_name": "Avery Archer", "attendee_id": "90000001",
        "class_number": "26MB1", "class_p4_id": "2000001", "class_name": "Chess",
        "days": "MoTuWeTh", "period_name": "A Block", "start_time": "09:00 AM",
        "start_time_24h": "09:00:00", "location": "Pavilion",
        "has_requirements": True, "class_completed": False,
        "raw_class_name": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
    }
    return ClassRecord(**{**defaults, **overrides})
```

- [ ] **Step 2: `tests/factories/payloads.py`**

```python
# tests/factories/payloads.py
"""Synthetic ScoutingEvent-shaped payloads. Field names match the real API."""

from __future__ import annotations

from typing import Any

# All 18 real REQ_NBR_WEB_DISPLAY shapes observed in the corpus (values synthetic).
REQUIREMENT_NUMBER_SHAPES = [
    "#3b", "#3(b)", "6.a.1.", "#5(c)(1)", "#1", "2.", "4", "#7a.", "#8a(2)", "3.b.",
    "#2.Option.A.(1)", "#5.Option.D.(3)(a)", "#5.Option.A(1)", "#5..Opt.A.(1)",
    "#(c)", "Note.", "", "#4..Aaa.A.(1)",
]


def requirement_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "MDM_LKP_BADGE_REQ_ID": "r1", "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
        "MERIT_BADGE_NAME": "Chess", "REQ_NBR": "1", "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Discuss the history of chess.",
        "COMPLETED_REQ_FLAG": "0", "COMPLETED_CLASS_FLAG": "0",
        "REQ_ON_EVENT": "1", "PRESENT_DAYS": "MoTuWeTh",
    }
    row.update(overrides)
    return row


def requirement_payload(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": {"status": 1, "stack": []}, "data": rows or [requirement_row()]}


def schedule_payload(classes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # Field names MUST match what process_scout reads at scout_schedule_cli.py:515-529:
    # CLASS_NAME (raw), CLASS_NAME_ONLY (display), CLASS_NBR, classP4ID, PERIOD_NAME,
    # CLASS_STIME, STIME, LOCATION_ROOM_NAME, HAS_REQ, CLASS_COMPLETED. The attendee_id
    # is NOT read from the payload — it comes from the request's post_data (form_values).
    # `classes is None` -> one default class; `classes == []` -> a ZERO-class payload
    # (distinguishing None from [] lets Slice 1b characterize the no-class case).
    default = {
        "classP4ID": "2000001",
        "CLASS_NAME": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
        "CLASS_NAME_ONLY": "Chess", "CLASS_NBR": "26MB1",
        "PERIOD_NAME": "A Block", "CLASS_STIME": "09:00 AM", "STIME": "09:00:00",
        "LOCATION_ROOM_NAME": "Pavilion", "HAS_REQ": "1", "CLASS_COMPLETED": "0",
    }
    rows = [default] if classes is None else classes
    return {"status": {"status": 1}, "data": rows}
```

- [ ] **Step 3: Smoke test + verify**

```python
# tests/factories/test_factories_smoke.py
from tests.factories.payloads import REQUIREMENT_NUMBER_SHAPES, requirement_payload
from tests.factories.records import make_requirement


def test_factories_build():
    assert make_requirement(requirement_number="#3b").requirement_number == "#3b"
    assert len(requirement_payload()["data"]) == 1
    assert len(REQUIREMENT_NUMBER_SHAPES) == 18
```

```bash
uv run pytest tests/factories -q
```
Expected: passed.

- [ ] **Step 4: Commit**

```bash
git add tests/factories
git commit -m "test: add deterministic synthetic factories and API-shaped payloads"
```

---

### Task 5: Privacy scanner and fixture tripwire

**Goal:** A scanner that fails closed if likely-private data appears under `tests/`, with
two layers: (a) **pattern checks** that run everywhere including CI (live QR tokens), and
(b) an optional **corpus cross-reference** that, where the private `raw_data/` corpus is
present, scans committed content *and filenames* for any real name, attendee ID, or
surname fragment — the manual pre-commit PII sweep, codified as a committed tool. A
conftest tripwire runs both before the suite.

*Carried forward from the original foundation plan:* the self-verifying discipline (scan
output for every original value, longest-first, report the file never the value) and its
leaky-input test suite. The real→committed fixture scrubber is **not** carried forward —
committed fixtures are synthetic (spec D7); a local-corpus scrubber is deferred to the
private-corpus work (D12).

**Files:**
- Create: `tools/check_private_data.py`
- Modify: `tests/conftest.py` (add the tripwire half)
- Create: `tests/privacy/test_fixture_hygiene.py`

**Acceptance Criteria:**
- [ ] Pattern layer flags a `scoutingevent.com/mobile/?t=` token not starting with `TESTTOKEN`
- [ ] `--corpus <dir>` layer flags a real name or attendee ID from the corpus appearing in
      a scanned file's **contents or filename**, including a surname fragment (word-boundary, len > 3)
- [ ] A name that is a substring of another (`Ann Lee` inside `Ann Leeson`) is still caught
- [ ] Reports `private-data findings: 0` on clean synthetic fixtures, **never echoing the matched value**
- [ ] Session tripwire runs pattern checks always and corpus checks when `raw_data/` exists; exits non-zero on findings

**Verify:** `uv run python tools/check_private_data.py --corpus raw_data tests && uv run pytest tests/privacy -q`

**Steps:**

- [ ] **Step 1: RED tests (pattern + corpus + leaky-input suite)**

```python
# tests/privacy/test_fixture_hygiene.py
from pathlib import Path

from tools.check_private_data import scan_corpus, scan_patterns


# Build the sentinel token dynamically so this test FILE contains no live-token literal —
# otherwise the Verify step (`check_private_data.py tests`) would flag its own source.
_MOBILE = "scoutingevent.com/" + "mobile"
_LIVE = "REAL" + "TOKEN123"


def test_clean_fixtures_have_no_pattern_findings():
    assert scan_patterns([Path("tests/fixtures"), Path("tests/factories")]) == []


def test_pattern_flags_a_live_token(tmp_path):
    (tmp_path / "leak.json").write_text(f"url: https://{_MOBILE}/?t={_LIVE}", encoding="utf-8")
    assert scan_patterns([tmp_path])


def test_corpus_flags_a_real_name_in_contents(tmp_path):
    (tmp_path / "leak.md").write_text("notes about Ann Leeson", encoding="utf-8")
    findings = scan_corpus([tmp_path], names={"Ann Leeson"}, ids=set())
    # Findings must never echo the matched value, in path OR reason.
    assert findings and all("Ann Leeson" not in f"{path} {reason}" for path, reason in findings)


def test_corpus_flags_a_substring_name(tmp_path):
    """'Ann Lee' must still be caught when embedded in other text."""
    (tmp_path / "leak.md").write_text("Ann Leeson met Ann Lee", encoding="utf-8")
    assert scan_corpus([tmp_path], names={"Ann Lee"}, ids=set())


def test_corpus_flags_an_id_in_a_filename_without_echoing_it(tmp_path):
    leak_id = "88" + "880001"                       # not a literal, and synthetic anyway
    (tmp_path / f"{leak_id}-report.html").write_text(f'<tr data-attendee="{leak_id}">', encoding="utf-8")
    findings = scan_corpus([tmp_path], names=set(), ids={leak_id})
    assert findings                                  # matched (filename + attribute)
    assert all(leak_id not in f"{path} {reason}" for path, reason in findings)   # redacted


def test_corpus_flags_a_surname_fragment(tmp_path):
    (tmp_path / "leak.md").write_text("a note mentioning Leeson somewhere", encoding="utf-8")
    assert scan_corpus([tmp_path], names={"Ann Leeson"}, ids=set())


def test_clean_content_has_no_corpus_findings(tmp_path):
    (tmp_path / "ok.md").write_text("Avery Archer is synthetic", encoding="utf-8")
    assert scan_corpus([tmp_path], names={"Ann Leeson"}, ids={"88" + "880001"}) == []
```

- [ ] **Step 2: Run RED**, expect `ModuleNotFoundError: tools.check_private_data`.

- [ ] **Step 3: Implement the scanner (pattern layer + corpus layer)**

```python
# tools/check_private_data.py
"""Fail closed if committed content looks like real Scout data.

Two layers:
  * patterns  — run everywhere (CI included): live scoutingevent QR tokens.
  * corpus    — run where the private raw_data corpus is present: cross-reference
                every real name, attendee ID, and surname fragment against scanned
                file contents AND filenames, longest-first.

Findings report the offending file and a reason ONLY — never the matched value — so
the scanner itself cannot leak what it found.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

LIVE_TOKEN = re.compile(r"scoutingevent\.com/mobile/[^\s\"'<>]*?[?&]t=([A-Za-z0-9_-]+)")


def _iter_files(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                yield path


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan_patterns(roots: list[Path]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in _iter_files(roots):
        text = _read(path)
        if text is None:
            continue
        for token in LIVE_TOKEN.findall(text):
            if not token.startswith("TESTTOKEN"):
                findings.append((str(path), "live-qr-token"))
    return findings


def load_corpus_identifiers(corpus_dir: Path) -> tuple[set[str], set[str]]:
    """Real names + attendee IDs from a private corpus's classes.csv files (local only)."""
    names: set[str] = set()
    ids: set[str] = set()
    for classes in corpus_dir.glob("*/classes.csv"):
        with classes.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("scout_name"):
                    names.add(row["scout_name"].strip())
                if row.get("attendee_id"):
                    ids.add(row["attendee_id"].strip())
    return names, ids


def _redact(path: Path, values: list[str]) -> str:
    """Report a path with any matched sensitive value masked — a filename can itself BE the
    leak, so the finding must not echo it. Also hashes the parent dir name if it matches."""
    reported = str(path)
    for value in values:
        if value and value in reported:
            reported = reported.replace(value, "***")
    return reported


def scan_corpus(roots: list[Path], names: set[str], ids: set[str]) -> list[tuple[str, str]]:
    # Full values (longest first, so a substring name never masks its superstring) plus
    # surname-level fragments matched on a word boundary.
    exact = sorted((v for v in (names | ids) if v), key=len, reverse=True)
    fragments = {p for n in names for p in n.split() if len(p) > 3}
    frag_res = {p: re.compile(rf"\b{re.escape(p)}\b") for p in fragments}

    findings: list[tuple[str, str]] = []
    for path in _iter_files(roots):
        blob = str(path)  # filenames leak too
        text = _read(path)
        if text is not None:
            blob += "\n" + text
        if any(value in blob for value in exact):
            findings.append((_redact(path, exact), "corpus-exact"))   # never echo the value
            continue
        matched_frags = [p for p, rx in frag_res.items() if rx.search(blob)]
        if matched_frags:
            findings.append((_redact(path, matched_frags), "corpus-fragment"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--corpus", type=Path, default=None,
                        help="Private corpus dir; enables real-value cross-reference when present.")
    args = parser.parse_args(argv)

    findings = scan_patterns(args.roots)
    if args.corpus and args.corpus.is_dir():
        names, ids = load_corpus_identifiers(args.corpus)
        findings += scan_corpus(args.roots, names, ids)

    print(f"private-data findings: {len(findings)}")
    for path, reason in findings:
        print(f"  {path}: {reason}")  # reason only, never the matched value
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the tripwire to `tests/conftest.py`**

Append:

```python
from pathlib import Path

import pytest

from tools.check_private_data import load_corpus_identifiers, scan_corpus, scan_patterns

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def fixtures_are_sanitized() -> None:
    roots = [Path(__file__).parent / "fixtures", Path(__file__).parent / "factories"]
    findings = scan_patterns(roots)
    corpus = _REPO_ROOT / "raw_data"
    if corpus.is_dir():  # local strictness; degrades to pattern-only in CI
        names, ids = load_corpus_identifiers(corpus)
        findings += scan_corpus(roots, names, ids)
    assert not findings, f"private-data findings under tests/: {len(findings)}"
```

- [ ] **Step 5: Run GREEN + the full sweep**

```bash
uv run pytest tests/privacy -q
uv run python tools/check_private_data.py --corpus raw_data tests
```
Expected: passed; `private-data findings: 0`. If the corpus layer reports anything, **stop
and remove the leak — do not commit.**

- [ ] **Step 6: Commit**

```bash
git add tools/check_private_data.py tests/conftest.py tests/privacy/test_fixture_hygiene.py
git commit -m "test: fail-closed privacy scanner (patterns + corpus cross-reference) and tripwire"
```

---

### Task 6: Local corpus verification tool

**Goal:** Confirm the synthetic factories match reality: a tool that reads the private
`raw_data/` corpus and prints aggregate shape/flag counts only, so the synthetic shapes
can be checked against the real corpus without committing any real data.

**Files:**
- Create: `tools/verify_corpus.py`
- Create: `tests/tools/test_verify_corpus.py`

**Acceptance Criteria:**
- [ ] Prints requirement/payload counts, the 5 flag combos, and requirement-number shape counts
- [ ] Emits no names, IDs, descriptions, or URLs (test-enforced)
- [ ] Exits non-zero if the corpus dir is absent

**Verify:** `uv run pytest tests/tools/test_verify_corpus.py -q && uv run python tools/verify_corpus.py raw_data`

**Steps:**

- [ ] **Step 1: RED test**

```python
# tests/tools/test_verify_corpus.py
import json
from tools.verify_corpus import number_shape, summarize_run


def test_number_shape_collapses_values():
    assert number_shape("#3b") == "#Na"
    assert number_shape("#2.Option.A.(1)") == "#N.Aaaaaa.A.(N)"


def test_summary_emits_only_aggregates(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "avery-archer-sched.json").write_text(json.dumps({
        "status": {"status": 1}, "data": [{
            "REQ_NBR_WEB_DISPLAY": "#3b", "REQ_DESCR": "Avery secret text",
            "COMPLETED_REQ_FLAG": "1", "COMPLETED_CLASS_FLAG": "0"}]}), encoding="utf-8")
    summary = summarize_run(tmp_path)
    blob = json.dumps(summary)
    assert summary["requirements"] == 1
    assert summary["flag_combos"]["('1', '0')"] == 1
    assert "Avery" not in blob and "secret" not in blob
```

- [ ] **Step 2: Run RED**, expect `ModuleNotFoundError`.

- [ ] **Step 3: Implement** (same logic as the scanner, aggregates only)

```python
# tools/verify_corpus.py
"""Reproduce the design spec's corpus counts. Aggregate output only — never PII."""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any


def number_shape(value: str) -> str:
    shaped = re.sub(r"[A-Z]", "A", str(value))
    shaped = re.sub(r"[a-z]", "a", shaped)
    return re.sub(r"[0-9]+", "N", shaped)


def summarize_run(run_dir: Path) -> dict[str, Any]:
    raw = run_dir / "raw"
    payloads = sorted(raw.glob("*.json")) if raw.is_dir() else []
    requirements = 0
    flags: collections.Counter[str] = collections.Counter()
    shapes: collections.Counter[str] = collections.Counter()
    for p in payloads:
        try:
            data = json.loads(p.read_text(encoding="utf-8")).get("data") or []
        except (OSError, json.JSONDecodeError):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            requirements += 1
            flags[str((row.get("COMPLETED_REQ_FLAG"), row.get("COMPLETED_CLASS_FLAG")))] += 1
            shapes[number_shape(row.get("REQ_NBR_WEB_DISPLAY") or "")] += 1
    return {"raw_payloads": len(payloads), "requirements": requirements,
            "flag_combos": dict(flags), "number_shapes": dict(shapes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    if not args.corpus.is_dir():
        print(f"corpus not found: {args.corpus}", file=sys.stderr)
        return 2
    for run in sorted(p for p in args.corpus.iterdir() if p.is_dir()):
        s = summarize_run(run)
        print(f"{run.name}: {s['requirements']} requirements, {s['raw_payloads']} payloads")
        for combo, n in sorted(s["flag_combos"].items()):
            print(f"    flags {combo}: {n}")          # the 5 (REQ, CLASS) combinations
        for shape, n in sorted(s["number_shapes"].items(), key=lambda kv: -kv[1]):
            print(f"    shape {shape!r}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: GREEN + reproduce the numbers**

```bash
uv run pytest tests/tools/test_verify_corpus.py -q
uv run python tools/verify_corpus.py raw_data
```
Expected: each run reports **4858 requirements / 120 payloads** and prints all 5 flag
combos (including the 309-row `(None, None)`). Run locally where `raw_data/` exists
(execution rule 8). If counts differ, update the spec (the numbers are the claim under
test), not the tool.

- [ ] **Step 5: Commit**

```bash
git add tools/verify_corpus.py tests/tools/test_verify_corpus.py
git commit -m "test: add aggregate-only corpus verifier to check synthetic shapes vs reality"
```

---

### Task 7: Characterize `requirement_path` and add the test CI job

**Goal:** Pin the current parse for all 18 shapes (including the two suspect ones, as-is),
a property test that it never raises, and add the `test` job to CI now that tests exist.

**Files:**
- Create: `tests/characterization/test_requirement_path.py`
- Modify: `.github/workflows/ci.yml`

**Acceptance Criteria:**
- [ ] All 18 shapes covered as a `parametrize` table
- [ ] `Note.` → `('7','note')` and `""` → `()` pinned as-is, comment-marked unresolved
- [ ] Hypothesis: `requirement_path` never raises on arbitrary strings
- [ ] CI `test` job on ubuntu + windows

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/characterization/test_requirement_path.py -q`

**Steps:**

- [ ] **Step 1: Characterization tests**

```python
# tests/characterization/test_requirement_path.py
"""Pin current requirement_path behavior before any code moves.
Suspect cases are pinned AS-IS; a fix is a separate change with its own RED test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import requirement_path  # noqa: E402


@pytest.mark.parametrize(
    ("number", "top", "path", "new_top"),
    [
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
        ("#2.Option.A.(1)", None, ("2", "option", "a", "1"), "2"),
        ("#5.Option.D.(3)(a)", None, ("5", "option", "d", "3", "a"), "5"),
        ("#5.Option.A(1)", None, ("5", "option", "a", "1"), "5"),
        ("#5..Opt.A.(1)", None, ("5", "opt", "a", "1"), "5"),
        ("#4..Aaa.A.(1)", None, ("4", "aaa", "a", "1"), "4"),  # 18th distinct shape
        ("#(c)", "7", ("7", "c"), "7"),
        # SUSPECT: label row becomes a CHILD of the prior requirement. Unresolved.
        ("Note.", "7", ("7", "note"), "7"),
        # SUSPECT: empty number AND empty description (402 real rows). Unresolved.
        # The two rows below are ONE shape ("") in two contexts (no top / inherited top),
        # not two of the 18 shapes — they exercise the top-level-inheritance branch.
        ("", None, (), None),
        ("", "7", (), "7"),
    ],
)
def test_requirement_path_pins_current_behavior(number, top, path, new_top):
    got_path, got_top = requirement_path(number, top)
    assert got_path == path
    assert got_top == new_top


@given(st.text(max_size=40))
def test_requirement_path_never_raises(value):
    got, _ = requirement_path(value, None)
    assert isinstance(got, tuple)
```

- [ ] **Step 2: Run — expect all PASS.** A failure means the expectation is wrong (this is
  characterization); correct the expected value from observed output, do not touch
  `scout_schedule_cli.py`.

```bash
uv run pytest tests/characterization/test_requirement_path.py -q
```

- [ ] **Step 3: Add the `test` job to `.github/workflows/ci.yml`**

```yaml
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix: { os: [ubuntu-latest, windows-latest] }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv python install 3.12
      # --all-extras: the characterization suite imports scout_schedule_cli, which imports
      # Playwright + openpyxl at module scope. raw_data/ is absent in CI, so the corpus
      # layer of the privacy scanner degrades to pattern-only automatically.
      - run: uv sync --locked --all-extras
      - run: uv run pytest --cov --cov-report=term-missing -q
```

- [ ] **Step 4: Commit**

```bash
git add tests/characterization/test_requirement_path.py .github/workflows/ci.yml
git commit -m "test: characterize requirement_path across all 18 real shapes"
```

---

### Task 8: Characterize inference (both consumers, non-mutation, id() selection)

**Goal:** Pin `annotate_requirement_statuses` and `build_missing_requirements`: the copy
(non-mutation), choice thresholds, both consumers, the `id()`-keyed leaf/ancestor
selection that Slice 2 must re-express, the exclusions, and the same-name MERGE defect.

**Files:**
- Create: `tests/characterization/test_inference.py`

**Acceptance Criteria:**
- [ ] Input dicts are not mutated (guards `:672`)
- [ ] Choice threshold pinned (`Do TWO` → `complete_check` at 2 of 3)
- [ ] Leaf selection + incomplete-ancestor inclusion pinned (guards the `:801-835` `id()` walk)
- [ ] `(not used)` filter and `requirement_type_id == "3"` exclusion pinned
- [ ] The same-name MERGE is pinned as `test_KNOWN_DEFECT_...` (Task 11 replaces it)

**Verify:** `uv run pytest tests/characterization/test_inference.py -q`

**Steps:**

- [ ] **Step 1: Tests**

```python
# tests/characterization/test_inference.py
"""Pin inference before decomposition. KNOWN_DEFECT pins today's WRONG merge on purpose."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import (  # noqa: E402
    annotate_requirement_statuses, build_missing_requirements, choice_requirement_count,
)
from tests.factories.records import make_requirement  # noqa: E402


def test_annotate_does_not_mutate_input():
    rows = [asdict(make_requirement(requirement_number="#1"))]
    before = [dict(r) for r in rows]
    annotate_requirement_statuses(rows)
    assert rows == before


def test_choice_parent_completes_at_threshold():
    rows = [
        asdict(make_requirement(requirement_number="#2", requirement_id="p",
                                description="Do TWO of the following.")),
        asdict(make_requirement(requirement_number="#2a", requirement_id="c1", completed_requirement=True)),
        asdict(make_requirement(requirement_number="#2b", requirement_id="c2", completed_requirement=True)),
        asdict(make_requirement(requirement_number="#2c", requirement_id="c3")),
    ]
    parent = next(r for r in annotate_requirement_statuses(rows) if r["requirement_id"] == "p")
    assert parent["choice_required_count"] == 2
    assert parent["calculated_status"] == "complete_check"


def test_choice_count_handles_corpus_verbs():
    assert choice_requirement_count("Do TWO of the following.") == 2
    assert choice_requirement_count("Choose ONE of the following options.") == 1
    assert choice_requirement_count("Select two of the following.") == 2
    assert choice_requirement_count("Explain the following terms") is None


def _scout(reqs):
    return {"name": "Avery Archer", "attendee_id": "90000001", "classes": [],
            "requirements": reqs, "errors": []}


def test_leaf_and_ancestor_selection():
    reqs = [
        asdict(make_requirement(requirement_number="#3", requirement_id="parent",
                                description="Do the following.")),
        asdict(make_requirement(requirement_number="#3b", requirement_id="leaf")),
    ]
    entries = build_missing_requirements([_scout(reqs)])["Avery Archer"]["Chess"]
    by_num = {e["requirement_number"]: e for e in entries}
    assert by_num["#3b"]["is_leaf"] is True
    assert by_num["#3"]["is_leaf"] is False


def test_headers_and_not_used_excluded():
    reqs = [
        asdict(make_requirement(requirement_number="#4", requirement_id="hdr", requirement_type_id="3")),
        asdict(make_requirement(requirement_number="#5", requirement_id="dead",
                                description="Forge ...(not used)")),
        asdict(make_requirement(requirement_number="#6", requirement_id="live")),
    ]
    nums = {e["requirement_number"] for e in build_missing_requirements([_scout(reqs)])["Avery Archer"]["Chess"]}
    assert "#6" in nums and "#4" not in nums and "#5" not in nums


def test_KNOWN_DEFECT_same_named_attendees_merge():
    """DEFECT (spec defect #1). Pins today's WRONG behavior; Task 11 replaces this test."""
    def scout(aid, rid, num):
        return {"name": "Avery Archer", "attendee_id": aid, "classes": [], "errors": [],
                "requirements": [asdict(make_requirement(attendee_id=aid, requirement_id=rid,
                                                         requirement_number=num, merit_badge_name="Chess"))]}
    grouped = build_missing_requirements([scout("90000001", "r1", "#1"), scout("90000002", "r2", "#2")])
    assert list(grouped) == ["Avery Archer"]           # ONE bucket for TWO people — the bug
    assert len(grouped["Avery Archer"]["Chess"]) == 2
```

- [ ] **Step 2: Run — expect all PASS** (characterization). Reconcile expectations to
  observed output if any status differs.

```bash
uv run pytest tests/characterization/test_inference.py -q
```

- [ ] **Step 3: Commit**

```bash
git add tests/characterization/test_inference.py
git commit -m "test: characterize inference incl. non-mutation, id() selection, name-merge defect"
```

---

### Task 9: Characterize `process_scout`, loaders, PDF matrix, CSV headers

**Goal:** Pin the browser-free orchestration path (monkeypatched), retry count, dedup, the
input loaders, the PDF decode/error matrix, and the exact CSV headers.

**Files:**
- Create: `tests/characterization/test_process_scout.py`
- Create: `tests/characterization/test_inputs_and_outputs.py`

**Acceptance Criteria:**
- [ ] `process_scout` runs with no real browser via monkeypatched `navigate_and_trigger_schedule`/`discover_name`/`post_requirement`
- [ ] Retry pinned at exactly 3 attempts; a failing scout accumulates an error, does not raise
- [ ] Both CSV headers asserted literally (guards `__dataclass_fields__` order at `:1666`,`:1671`)
- [ ] At least one loader (`load_csv`) and the attendee-CSV schema pinned

**Verify:** `uv run pytest tests/characterization -q`

**Steps:**

- [ ] **Step 1: `process_scout` characterization**

```python
# tests/characterization/test_process_scout.py
"""Characterize process_scout WITHOUT a browser (monkeypatch the 3 module-level fns)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402
from tests.factories.payloads import requirement_payload, schedule_payload  # noqa: E402


class _Request:
    # process_scout reads schedule_response.request.post_data (:480) and form_values
    # extracts attendeeID from it — that is the source of attendee_id, NOT the payload.
    def __init__(self, post_data: str = "attendeeID=90000001"):
        self.post_data = post_data


class _Resp:
    def __init__(self, payload, post_data: str = "attendeeID=90000001"):
        self._p = payload
        self.request = _Request(post_data)
    async def json(self): return self._p


class _Page:
    # process_scout calls these on the page BEFORE navigate (:472-476); the fake must
    # provide them or the test raises AttributeError before reaching the payload.
    def set_default_timeout(self, _ms): return None
    def on(self, _event, _cb): return None
    async def evaluate(self, *a, **k): return None
    async def wait_for_timeout(self, _ms): return None
    async def close(self): return None


class _Ctx:
    async def new_page(self): return _Page()
    async def route(self, *a, **k): return None
    async def close(self): return None


class _Browser:
    async def new_context(self, **k): return _Ctx()


def _args(**o):
    return argparse.Namespace(**{"timeout": 45, "request_delay_ms": 0,
                                 "allow_dead_assets": True, "headed": False, "channel": None, **o})


async def test_process_scout_builds_records_without_browser(monkeypatch, tmp_path):
    async def nav(page, url, t): return _Resp(schedule_payload())
    async def name(page, fb): return fb
    async def post(page, aid, cpid): return requirement_payload()
    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", post)

    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert result.classes[0].class_name == "Chess"
    assert result.requirements[0].requirement_number == "#1"
    assert result.errors == []


async def test_failing_scout_accumulates_error(monkeypatch, tmp_path):
    async def boom(page, url, t): raise RuntimeError("schedule exploded")
    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", boom)
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert result.errors and "schedule exploded" in " ".join(result.errors)


async def test_requirement_fetch_retries_three_times(monkeypatch, tmp_path):
    async def nav(page, url, t): return _Resp(schedule_payload())
    async def name(page, fb): return fb
    attempts = {"n": 0}
    async def flaky(page, aid, cpid):
        attempts["n"] += 1
        raise RuntimeError("transient")
    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", flaky)
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert attempts["n"] == 3  # retry policy is range(1, 4) at scout_schedule_cli.py:538
```

- [ ] **Step 2: CSV headers + loader**

```python
# tests/characterization/test_inputs_and_outputs.py
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import ClassRecord, RequirementRecord, write_csv  # noqa: E402
from tests.factories.records import make_class, make_requirement  # noqa: E402

CLASS_HEADER = ["scout_name", "attendee_id", "class_number", "class_p4_id", "class_name",
                "days", "period_name", "start_time", "start_time_24h", "location",
                "has_requirements", "class_completed", "raw_class_name"]
REQ_HEADER = ["scout_name", "attendee_id", "class_number", "class_p4_id", "merit_badge_name",
              "requirement_id", "requirement_type_id", "requirement_number", "description",
              "completed_requirement", "completed_class", "requirement_on_event", "present_days"]


def _header(path):
    with path.open("r", encoding="utf-8-sig", newline="") as s:
        return next(csv.reader(s))


def test_class_csv_header_stable(tmp_path):
    p = tmp_path / "c.csv"
    write_csv(p, [make_class()], [f.name for f in ClassRecord.__dataclass_fields__.values()])
    assert _header(p) == CLASS_HEADER


def test_requirement_csv_header_stable(tmp_path):
    p = tmp_path / "r.csv"
    write_csv(p, [make_requirement()], [f.name for f in RequirementRecord.__dataclass_fields__.values()])
    assert _header(p) == REQ_HEADER
```

- [ ] **Step 3: Run** — reconcile fakes if `process_scout` calls a method not on a fake
  (add it; do not edit production). Expect all PASS.

```bash
uv run pytest tests/characterization -q
```

- [ ] **Step 4: Commit**

```bash
git add tests/characterization/test_process_scout.py tests/characterization/test_inputs_and_outputs.py
git commit -m "test: characterize process_scout via monkeypatch and pin CSV headers"
```

---

### Task 10: Attendee identity + per-run UUIDv4 output identity (in the flat script)

**Goal:** Typed identity: `AttendeeId` fails closed on blank; `RunIdentity` assigns a
stable-within-run UUIDv4 per attendee for **output**; the raw ID never enters a filename.

> **Where this lives (decided after review):** Slice 1 is *in-place fixes before the
> restructure*, and the code that uses these helpers — `scout_schedule_cli.py` — is a
> **flat script the launcher ships via `source_sync.py`**. `src/scoutmb` is **not** shipped.
> So the helpers are defined **inside `scout_schedule_cli.py`**, not in `src/scoutmb`, or the
> installed app would `ModuleNotFoundError` on launch. Slice 2 moves them into
> `scoutmb.core.identity` *together with* the launcher wiring, under parity.

**Files:**
- Modify: `scout_schedule_cli.py` (add `MissingAttendeeId`, `AttendeeId`, `RunIdentity` near the top)
- Test: `tests/unit/test_identity.py`

**Acceptance Criteria:**
- [ ] `AttendeeId.parse("  ")` raises `MissingAttendeeId`
- [ ] `RunIdentity.output_id(aid)` returns a v4 UUID, stable within the instance, distinct per attendee
- [ ] `output_id` never contains the raw attendee ID
- [ ] No production import of `scoutmb` is introduced (the launcher does not ship it)

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/unit/test_identity.py -q`

**Steps:**

- [ ] **Step 1: RED test** (imports from the flat script, not `scoutmb`)

```python
# tests/unit/test_identity.py
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import AttendeeId, MissingAttendeeId, RunIdentity  # noqa: E402


def test_blank_attendee_id_fails_closed():
    with pytest.raises(MissingAttendeeId):
        AttendeeId.parse("   ")


def test_valid_attendee_id_round_trips():
    assert AttendeeId.parse("90000001").value == "90000001"


def test_output_id_is_uuid4_stable_within_run_and_distinct():
    run = RunIdentity()
    a = run.output_id(AttendeeId.parse("90000001"))
    b = run.output_id(AttendeeId.parse("90000002"))
    assert uuid.UUID(a).version == 4
    assert a == run.output_id(AttendeeId.parse("90000001"))  # stable within run
    assert a != b
    assert "90000001" not in a


def test_two_runs_are_unlinkable():
    a = RunIdentity().output_id(AttendeeId.parse("90000001"))
    b = RunIdentity().output_id(AttendeeId.parse("90000001"))
    assert a != b
```

- [ ] **Step 2: Run RED**, expect `ImportError: cannot import name 'AttendeeId'`.

- [ ] **Step 3: Implement — add to `scout_schedule_cli.py`** (near the existing dataclasses,
  after the imports; the module already imports `uuid`? if not, add `import uuid`):

```python
class MissingAttendeeId(RuntimeError):
    """An attendee record arrived without the ID we use as identity."""

    def __init__(self, scout_name: str = "") -> None:
        self.scout_name = scout_name
        super().__init__(f"No attendee_id for {scout_name or 'an unnamed attendee'}")


@dataclass(frozen=True, slots=True)
class AttendeeId:
    value: str

    @classmethod
    def parse(cls, raw: str, scout_name: str = "") -> "AttendeeId":
        cleaned = str(raw or "").strip()
        if not cleaned:
            raise MissingAttendeeId(scout_name)
        return cls(cleaned)


@dataclass(slots=True)
class RunIdentity:
    """Assigns a UUIDv4 per attendee for one run. Stable within the run instance."""

    _by_attendee: dict[str, str] = field(default_factory=dict)

    def output_id(self, attendee: AttendeeId) -> str:
        existing = self._by_attendee.get(attendee.value)
        if existing is None:
            existing = str(uuid.uuid4())
            self._by_attendee[attendee.value] = existing
        return existing
```

  `dataclass`/`field` are already imported in `scout_schedule_cli.py`. `mypy files=["src","tools"]`
  does not cover the flat scripts, so there is no strict-mypy step here; the flat scripts are
  characterized, not type-gated, in Slice 1.

- [ ] **Step 4: GREEN**

```bash
uv sync --locked --all-extras && uv run pytest tests/unit/test_identity.py -q
```

- [ ] **Step 5: Commit**

```bash
git add scout_schedule_cli.py tests/unit/test_identity.py
git commit -m "feat: attendee identity + per-run UUIDv4 output identity (in the flat script)"
```

---

### Task 11: Fix the merge — key inference/grouping on attendee ID

**Goal:** Two same-named attendees never merge. Grouping, `by_key`, parent lookup, and
output bucketing key on the attendee ID; the display name becomes carried data. Deliberate
behavior change, RED-tested first.

**Files:**
- Modify: `scout_schedule_cli.py` (`:675`, `:786`, `:813-817`, `:838-840`, `:920`)
- Modify: `tests/characterization/test_inference.py` (delete the KNOWN_DEFECT test)
- Test: `tests/unit/test_inference_identity.py`

**Acceptance Criteria:**
- [ ] Two attendees, same name, different IDs → two separate groups
- [ ] `build_missing_requirements` returns `{attendee_id: {"display_name": str, "badges": {...}}}`
- [ ] KNOWN_DEFECT test removed; all other characterization tests pass (shape-updated where needed)

> **Scope note:** this fixes *grouping* identity only. Stripping the raw `attendee_id`/QR
> tokens from the output columns of `scouts.json`/`classes.csv`/`requirements.csv`/the email
> CSV is **Slice 2** (outputs move behind versioned schemas there). Slice 1 does not claim
> full D3/D14/D25.
>
> **Blank IDs:** a blank `attendee_id` cannot reach `build_missing_requirements` in practice
> — `process_scout` fails that scout closed at `scout_schedule_cli.py:482`. The helper's
> blank branch is therefore defensive; it keys on `scout_name` (matching the degenerate
> pre-fix behavior) rather than fabricating identity, and is not separately tested because it
> is unreachable through the production path.

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/ -q`

**Steps:**

- [ ] **Step 1: RED test**

```python
# tests/unit/test_inference_identity.py
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import build_missing_requirements  # noqa: E402
from tests.factories.records import make_requirement  # noqa: E402


def _scout(aid, rid, num):
    return {"name": "Avery Archer", "attendee_id": aid, "classes": [], "errors": [],
            "requirements": [asdict(make_requirement(attendee_id=aid, requirement_id=rid,
                                                     requirement_number=num, merit_badge_name="Chess"))]}


def test_same_named_attendees_stay_separate():
    grouped = build_missing_requirements([_scout("90000001", "r1", "#1"), _scout("90000002", "r2", "#2")])
    assert len(grouped) == 2
    for entry in grouped.values():
        assert entry["display_name"] == "Avery Archer"
        assert len(entry["badges"]["Chess"]) == 1
```

- [ ] **Step 2: Run RED** — `assert len(grouped) == 2` gets 1, and `KeyError: display_name`.

- [ ] **Step 3: Add the key helper above `annotate_requirement_statuses`**

```python
def _attendee_key_for(item: dict[str, Any]) -> str:
    """Grouping identity: the attendee ID, never the display name. Two attendees can
    share a name; merging them silently corrupts both.

    A blank attendee_id cannot occur through the production path (process_scout fails a
    scout closed at :482 when the schedule request has no attendeeID), so the blank branch
    is defensive only. It keys on scout_name — which does not fragment a single scout across
    its requirements the way requirement_id would, and does not depend on id(item), which is
    unstable across the dict copies this function makes.
    """
    attendee_id = str(item.get("attendee_id") or "").strip()
    if attendee_id:
        return attendee_id
    return f"name:{str(item.get('scout_name') or '')}"
```

- [ ] **Step 4: Rekey the four sites**

`:675` grouping:
```python
        grouped.setdefault((_attendee_key_for(item), str(item.get("class_p4_id") or "")), []).append(item)
```
`:786` `by_key`:
```python
    by_key = {
        (_attendee_key_for(item), str(item.get("class_p4_id") or ""), str(item.get("requirement_number") or "")): item
        for item in annotated
    }
```
`:813-817` `parent_key`:
```python
            parent_key = (_attendee_key_for(current), str(current.get("class_p4_id") or ""), str(parent_number))
```
`:838-840` output bucket (and change the return annotation at `:771` to `dict[str, dict[str, Any]]`):
```python
        attendee_key = _attendee_key_for(item)
        badge_name = str(item.get("merit_badge_name") or "")
        bucket = grouped.setdefault(attendee_key, {"display_name": str(item.get("scout_name") or ""), "badges": {}})
        bucket["badges"].setdefault(badge_name, []).append(entry)
```

- [ ] **Step 5: Update `write_email_reports` for the new shape** (`:920`)

```python
        attendee_key = str(scout.get("attendee_id") or "").strip() or f"unresolved-{scout_name}"
        bucket = missing.get(attendee_key) or {"display_name": scout_name, "badges": {}}
        badge_groups = bucket["badges"]
```

- [ ] **Step 6: Delete the KNOWN_DEFECT test** from `tests/characterization/test_inference.py`.

- [ ] **Step 7: Run the suite; shape-update the Task 8 tests** that read the old return
  shape — change `[...]["Avery Archer"]["Chess"]` to `[...]["90000001"]["badges"]["Chess"]`;
  assertions stay identical.

```bash
uv run pytest tests/ -q
```

- [ ] **Step 8: Commit**

```bash
git add scout_schedule_cli.py tests/unit/test_inference_identity.py tests/characterization/test_inference.py
git commit -m "fix: key inference grouping on attendee id, not display name (live data-merge bug)"
```

---

### Task 12: Collision-free output filenames via per-run UUIDv4

**Goal:** Raw-payload and email filenames are distinct per attendee and carry no raw ID —
readable name slug + a per-run UUID short form.

**Two write sites, two contexts (verified against the code — the earlier draft got this
wrong):**
- **Raw payloads** are written at `scout_schedule_cli.py:490` (schedule) and `:554`
  (requirements), both **inside `process_scout`**, sharing one `slug` computed at `:490`.
  `process_scout` is called only from `async_main` (`:1743`). A `RunIdentity` therefore has
  to be **passed into `process_scout`** — it cannot be reached from `async_main` otherwise.
- **Emails** are written at `:935` inside `write_email_reports`, which is called **two
  ways**: from `write_outputs` during a run *and* **independently from `ui/server.py:313`**
  (`generate_emails` re-reads `scouts.json` in a separate request, with no `RunIdentity` in
  scope). So `write_email_reports` must mint its **own** `RunIdentity` internally — that
  fixes both call paths at once.

Collision-freedom does not require the raw UUID and the email UUID to match (different
directories, different purposes): distinct `attendee_id`s always map to distinct UUIDs
within either `RunIdentity`. Cross-artifact/persisted identity for resume (spec D25's "run
checkpoint") is a Slice-2 concern (acquisition checkpointing) and is **not** implemented
here — noted as a follow-up.

**Files:**
- Modify: `scout_schedule_cli.py` — add `attendee_filename_stem` after `safe_slug`
  (`:595-597`); add a `run_identity` param to `process_scout`; use the stem at `:490`
  (covers `:554` via the shared `slug`); mint a local `RunIdentity` in `write_email_reports`
  and use the stem at `:935`; construct + pass a `RunIdentity` from `async_main`.
- Test: `tests/unit/test_output_filenames.py`

**Acceptance Criteria:**
- [ ] `attendee_filename_stem(name, output_id)` = `f"{safe_slug(name)}-{output_id (hyphens stripped)}"`
      — the **full** 32-hex UUID, not a truncation, so it is genuinely collision-free; no raw attendee ID
- [ ] Two same-named, different-ID attendees → **distinct raw filenames** (via `process_scout`) and **distinct email filenames** (via `write_email_reports`)
- [ ] `process_scout`'s new `run_identity` param defaults to `None` and self-creates, so Task 9's characterization calls keep working unchanged
- [ ] Stable within a run

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/unit/test_output_filenames.py -q`

**Steps:**

- [ ] **Step 1: RED tests** (helper + both write sites)

```python
# tests/unit/test_output_filenames.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402
from scout_schedule_cli import attendee_filename_stem  # noqa: E402
from tests.factories.records import make_requirement  # noqa: E402


def test_stem_hides_the_raw_id_and_carries_the_full_uuid():
    stem = attendee_filename_stem("Avery Archer", "1234abcd-ef00-4000-8000-000000000000")
    assert stem == "avery-archer-1234abcdef0040008000000000000000"  # full 32 hex, no hyphens


def test_stem_distinct_for_distinct_output_ids():
    assert attendee_filename_stem("Avery Archer", "aaaaaaaa-0000-4000-8000-000000000000") != \
           attendee_filename_stem("Avery Archer", "bbbbbbbb-0000-4000-8000-000000000000")


def test_email_reports_do_not_collide_for_same_named_attendees(tmp_path):
    """write_email_reports must produce distinct .txt/.html for two same-named attendees."""
    def scout(aid, rid):
        return {"name": "Avery Archer", "attendee_id": aid, "classes": [], "errors": [],
                "requirements": [dict(__import__("dataclasses").asdict(
                    make_requirement(attendee_id=aid, requirement_id=rid,
                                     requirement_number="#1", merit_badge_name="Chess")))]}
    cli.write_email_reports(tmp_path, [scout("90000001", "r1"), scout("90000002", "r2")])
    txt = sorted((tmp_path / "emails").glob("avery-archer-*.txt"))
    # Two same-named attendees -> two distinct email files, not one overwritten file.
    assert len(txt) == 2 and txt[0].name != txt[1].name


def test_process_scout_raw_filenames_are_distinct_for_same_named(monkeypatch, tmp_path):
    """The raw side (inside process_scout) must also not collide. Reuses the Task 9 fakes."""
    import asyncio

    from tests.factories.payloads import requirement_payload, schedule_payload
    # _Browser/_Resp/_Page from Task 9's test module; import or redefine minimal versions here.
    from tests.characterization.test_process_scout import _Browser, _Resp  # noqa: E402

    async def name(page, fb):
        return fb
    async def post(page, aid, cpid):
        return requirement_payload()
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", post)

    async def run(attendee_id):
        async def nav(page, url, t):
            return _Resp(schedule_payload(), post_data=f"attendeeID={attendee_id}")
        monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
        scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
        args = __import__("argparse").Namespace(
            timeout=45, request_delay_ms=0, allow_dead_assets=True, headed=False, channel=None)
        await cli.process_scout(_Browser(), scout, args, tmp_path)

    asyncio.run(run("90000001"))
    asyncio.run(run("90000002"))
    schedules = sorted(tmp_path.glob("avery-archer-*-schedule.json"))
    assert len(schedules) == 2 and schedules[0].name != schedules[1].name
```

> The email test only asserts distinctness if both scouts have missing requirements. Ensure
> the synthetic requirement is incomplete (the factory default `completed_requirement=False`
> satisfies this) so `missing_count > 0` and the files are written. The raw test drives two
> `process_scout` runs with distinct `attendeeID`s and asserts two distinct `-schedule.json`
> names.

- [ ] **Step 2: Run RED**, expect `ImportError: attendee_filename_stem` (then, once the
  helper exists, both collision tests fail because `:490`/`:935` still use `safe_slug`).

- [ ] **Step 3: Add the helper after `safe_slug`**

```python
def attendee_filename_stem(scout_name: str, output_id: str) -> str:
    """Readable, collision-free filename stem: name slug + the FULL per-run output UUID
    (hyphens stripped). The full UUID — never a truncation — guarantees distinct attendees
    get distinct filenames. Never the raw attendee_id (a bearer token that must not appear
    in a shareable filename)."""
    return f"{safe_slug(scout_name)}-{str(output_id).replace('-', '')}"
```

- [ ] **Step 4: Fix the raw side in `process_scout`.** `AttendeeId`/`RunIdentity` are defined
  in this same module (Task 10) — **no import needed**, and no `scoutmb` dependency. Add a
  parameter `run_identity: RunIdentity | None = None` to `process_scout`; at the top of its body add
  `run_identity = run_identity or RunIdentity()`. After `attendee_id` is confirmed non-blank
  (it raises at `:482` otherwise) and `result.name` is set (`:486`), compute
  `output_id = run_identity.output_id(AttendeeId.parse(attendee_id, result.name))` and
  replace `slug = safe_slug(result.name)` at `:490` with
  `slug = attendee_filename_stem(result.name, output_id)`. The `:554` requirements write
  reuses `slug`, so it is fixed automatically. The `None` default keeps Task 9's direct
  `process_scout(...)` test calls valid without change.

- [ ] **Step 5: Pass a shared `RunIdentity` from `async_main`.** Build
  `run_identity = RunIdentity()` before the scout loop and call
  `process_scout(browser, scout, args, raw_dir, run_identity)` at `:1743` so raw filenames
  are stable across the whole run.

- [ ] **Step 6: Fix the email side in `write_email_reports`.** Add
  `run_identity = RunIdentity()` at the top of the function (its own instance — the UI's
  `generate_emails` at `ui/server.py:313` calls this function directly with no shared
  identity, and this makes that path collision-free too). In the `if missing_count:` branch,
  replace `slug = safe_slug(scout_name)` at `:935` with:

```python
            output_id = run_identity.output_id(AttendeeId.parse(attendee_id, scout_name))
            slug = attendee_filename_stem(scout_name, output_id)
```

  `attendee_id` is already read at `:919`; this branch only runs for scouts with missing
  requirements, which always have a non-blank `attendee_id`, so `AttendeeId.parse` will not
  raise here.

- [ ] **Step 7: Run the suite**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 8: Commit**

```bash
git add scout_schedule_cli.py tests/unit/test_output_filenames.py
git commit -m "fix: collision-free raw and email filenames via per-run UUID (no raw id)"
```

---

### Task 13: Atomic single-file writes (user-facing writers)

**Goal:** A failed write never truncates the previous file. The **user-facing** writers —
`scouts.csv`, the report, and email files — write via same-dir temp + fsync + `os.replace`.

> **Scope (narrowed — see "Scope honesty"):** Slice 1 covers the writers whose loss hurts a
> user directly. The **full D11 contract** — exclusive same-dir temp, parent-directory fsync,
> a documented post-replace indeterminate-durability result, and routing *every* remaining
> JSON/CSV/raw artifact (`scouts.json`, `summary.json`, `errors.csv`, the raw payloads at
> `:490`/`:554`) — is **Slice 2**, where the writers move behind a `FileStore` port. Task 13
> does not claim full D11.

**Files:**
- Modify: `scout_schedule_cli.py` (add `atomic_write_text`; route `write_csv`, report, email files, and `missing_requirements.csv`), `pdf_to_scouts.py` (add its own `atomic_write_text`; route `write_attendees_csv`/`write_errors_csv`)
- Test: `tests/unit/test_atomic_write.py`

> **Location (flat-scripts decision):** `atomic_write_text` is defined **in each shipped flat
> script**, not in `src/scoutmb` (which the launcher does not ship). The two copies are ~10
> lines and diverge in Slice 2 when they move behind a `FileStore` port. `pdf_to_scouts.py`
> must not import `scout_schedule_cli` (that would pull Playwright into the PDF stage).

**Acceptance Criteria:**
- [ ] A failure **during the write** (injected `os.fsync`/`replace` failure or a raising
      render) leaves the original file byte-identical and leaves no `.tmp` behind
- [ ] A successful write replaces atomically and preserves bytes/encoding exactly (a
      `utf-8-sig` writer round-trips through a `utf-8-sig` read)
- [ ] `write_attendees_csv` preserves its exact 7-column `DictWriter` header and row mapping

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/unit/test_atomic_write.py -q`

**Steps:**

- [ ] **Step 1: RED tests** (encoding round-trip + failure injected *during* the write)

```python
# tests/unit/test_atomic_write.py
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scout_schedule_cli import atomic_write_text  # noqa: E402


def test_success_replaces_and_roundtrips_encoding(tmp_path):
    p = tmp_path / "scouts.csv"
    p.write_text("old", encoding="utf-8-sig")
    atomic_write_text(p, "new")                      # default encoding is utf-8-sig
    assert p.read_text(encoding="utf-8-sig") == "new"   # read with the SAME codec
    assert list(tmp_path.glob("*.tmp")) == []


def test_plain_utf8_roundtrips(tmp_path):
    p = tmp_path / "report.html"
    atomic_write_text(p, "<html>x</html>", encoding="utf-8")
    assert p.read_text(encoding="utf-8") == "<html>x</html>"


def test_failure_during_replace_preserves_original(tmp_path, monkeypatch):
    p = tmp_path / "scouts.csv"
    p.write_text("irreplaceable", encoding="utf-8-sig")

    def boom(_src, _dst):
        raise OSError("replace failed")
    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        atomic_write_text(p, "new content that must not land")
    assert p.read_text(encoding="utf-8-sig") == "irreplaceable"   # original intact
    assert list(tmp_path.glob("*.tmp")) == []                     # temp cleaned up
```

Add a self-guard for the PDF writer this task routes (its header was previously pinned by the
now-moved Task 16 — pin it here, since Task 13 changes this writer):

```python
def test_write_attendees_csv_header_unchanged_after_atomic_routing(tmp_path):
    import csv
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pdf_to_scouts import ExtractedAttendee, write_attendees_csv
    a = ExtractedAttendee(attendee_name="Avery Archer", name_as_printed="Avery Archer",
                          registrant_type="Youth", qr_data="https://example.invalid/?t=TESTTOKEN0001",
                          source_pdf="s.pdf", pdf_page=1, qr_decode_method="embedded")
    out = tmp_path / "scouts.csv"
    write_attendees_csv(out, [a])
    with out.open(encoding="utf-8-sig", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["Attendee Name", "Registrant Type", "QR Code Contents",
                      "Name as Printed", "Source PDF", "PDF Page", "QR Decode Method"]
```

> The failure test injects the fault **inside** `atomic_write_text` (at `os.replace`), so it
> exercises a real atomic stage — unlike evaluating a `boom()` argument before the call,
> which tests nothing. Reading with `utf-8-sig` (matching the writer) avoids a spurious BOM
> mismatch.

- [ ] **Step 2: Run RED**, expect `ModuleNotFoundError`.

- [ ] **Step 2: Run RED**, expect `ImportError: cannot import name 'atomic_write_text'`.

- [ ] **Step 3: Implement — add this to `scout_schedule_cli.py` AND (a copy) to `pdf_to_scouts.py`**
  (`os`/`Path` are already imported in both; if not, add them):

```python
def atomic_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Render-first, same-dir temp, fsync, atomic replace. A failed write never truncates
    the previous file. (Full D11 contract — exclusive temp, parent-dir fsync — is Slice 2.)"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # noqa: PTH105 - the failure test monkeypatches os.replace;
        #                        Path.replace would defeat that injection. Keep os.replace.
    finally:
        tmp.unlink(missing_ok=True)
```

  The `# noqa: PTH105` is required: ruff's PTH105 would rewrite `os.replace` to
  `Path.replace`, and Task 13's failure test monkeypatches `os.replace` — the rewrite would
  make that injection a no-op and the test would pass vacuously.

- [ ] **Step 4: Route the writers through it, preserving exact structure.**
  - `pdf_to_scouts.py:write_attendees_csv` (`:448`) and `write_errors_csv` (`:476`) use
    `csv.DictWriter` with a fixed 7-field / 5-field header and a per-row dict mapping.
    Render into an `io.StringIO` with the **same `DictWriter` and field mapping** (not
    `csv.writer`), keep `path.parent.mkdir(...)`, then `atomic_write_text(path, buf.getvalue())`.
  - `scout_schedule_cli.py`:
    - `write_csv` (`:600`) uses `utf-8-sig` — render its `DictWriter`/`asdict` rows into a
      buffer, then `atomic_write_text`.
    - `scouts.json`/`summary.json` (`utf-8`) and the report/email `.txt`/`.html` — wrap each
      `.write_text` as `atomic_write_text(path, rendered, encoding=...)` (matching the
      original encoding: `utf-8` for json/report/email, `utf-8-sig` for csv).
    - **`errors.csv`** (`:1679`) and **`missing_requirements.csv`** (`write_email_reports`,
      `:952`) are currently direct `DictWriter` streams — render each into a buffer and route
      through `atomic_write_text` too, or the "email files atomic" goal is only half met.
  - **Task 9 (CSV headers) and this task's own `write_attendees_csv` header test pin these —
    run them after each edit.** (The exhaustive artifact-schema matrix is Slice 1b's job.)

- [ ] **Step 5: Run the suite**

```bash
uv sync --locked --all-extras && uv run pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add pdf_to_scouts.py scout_schedule_cli.py tests/unit/test_atomic_write.py
git commit -m "fix: atomic single-file writes so a failed run preserves prior artifacts"
```

---

### Task 14: `UiSettings` with explicit `data_root` (close Hazard 1)

**Goal:** Data paths resolve explicitly, never from `__file__`, so the Slice-2 package move
cannot relocate user data.

> **Location (flat-scripts decision):** `UiSettings` is defined **inline in the shipped
> `ui/server.py`**, not in `src/scoutmb/ui` (unshipped). It uses a **stdlib** platform-dir
> helper (mirroring `bootstrap/paths.py`) — **no `platformdirs` dependency**, so nothing new
> needs adding to `requirements.txt` or the launcher. Slice 2 moves it to
> `scoutmb.ui.settings` and can adopt `platformdirs` then.

**Files:**
- Modify: `ui/server.py` (add `UiSettings` + `_platform_data_root`; rewire `:24-41`)
- Test: `tests/unit/test_ui_settings.py`

**Acceptance Criteria:**
- [ ] Order: explicit arg → `SCOUTMB_DATA_DIR` → OS data location (stdlib) → `Path.cwd()` **only** when `dev_mode`
- [ ] With neither an arg nor the env var and `dev_mode=False`, resolution is the OS data location, **not** `cwd`
- [ ] `ui/server.py` derives no DATA path from `__file__` (static-asset path may stay — it locates code)
- [ ] No `platformdirs` / `scoutmb` production dependency is introduced
- [ ] The app starts and `GET /api/status` returns 200 (Step 5)

**Verify:** `uv sync --locked --all-extras && uv run pytest tests/unit/test_ui_settings.py -q`

**Steps:**

- [ ] **Step 1: RED test** (imports `UiSettings` from the shipped `ui.server`)

```python
# tests/unit/test_ui_settings.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ui.server import UiSettings  # noqa: E402


def test_explicit_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path / "env"))
    assert UiSettings.resolve(data_root=tmp_path / "explicit").data_root == tmp_path / "explicit"


def test_env_used_without_arg(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path / "env"))
    assert UiSettings.resolve().data_root == tmp_path / "env"


def test_dev_mode_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("SCOUTMB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert UiSettings.resolve(dev_mode=True).data_root == tmp_path


def test_no_env_no_dev_uses_os_location_not_cwd(tmp_path, monkeypatch):
    """A misconfigured production launch must land in the OS data dir, never cwd."""
    monkeypatch.delenv("SCOUTMB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    root = UiSettings.resolve(dev_mode=False).data_root
    assert root != tmp_path and "ScoutingMeritBadges" in str(root)


def test_derived_paths_hang_off_root(tmp_path):
    s = UiSettings.resolve(data_root=tmp_path)
    assert s.scouts_csv == tmp_path / "scouts.csv"
    assert s.runs_dir == tmp_path / "runs"


def test_root_independent_of_module_location(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path))
    s = UiSettings.resolve()
    assert Path(__file__).parent not in s.data_root.parents
```

- [ ] **Step 2: Run RED**, expect `ImportError: cannot import name 'UiSettings'`.

- [ ] **Step 3: Implement — add `UiSettings` + a stdlib platform-dir helper to `ui/server.py`**
  (no new dependency; mirrors `bootstrap/paths.py`):

```python
APP_NAME = "ScoutingMeritBadges"
DATA_DIR_ENV = "SCOUTMB_DATA_DIR"


def _platform_data_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME / "data"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "data"
    return Path.home() / ".local" / "share" / APP_NAME / "data"


@dataclass(frozen=True, slots=True)
class UiSettings:
    """Where the UI reads/writes user data. NEVER derive a data path from __file__ —
    that ties irreplaceable data to the code's on-disk location, so moving or reinstalling
    silently relocates or destroys it (Hazard 1)."""

    data_root: Path

    @classmethod
    def resolve(cls, data_root: Path | None = None, dev_mode: bool = False) -> "UiSettings":
        if data_root is not None:
            return cls(Path(data_root))
        env = os.environ.get(DATA_DIR_ENV)
        if env:
            return cls(Path(env))
        if dev_mode:
            return cls(Path.cwd())
        return cls(_platform_data_root())

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

  `dataclass` and `sys`/`os`/`Path` are already imported in `ui/server.py` (add any missing).

- [ ] **Step 4: Rewire `ui/server.py:24-41`.** Replace the `REPO_ROOT`/`SCOUTS_CSV`/… block:

```python
SETTINGS = UiSettings.resolve(dev_mode=bool(os.environ.get("SCOUTMB_DEV")))
SCOUTS_CSV = SETTINGS.scouts_csv
PDF_UPLOADS_DIR = SETTINGS.pdf_uploads_dir
RUNS_DIR = SETTINGS.runs_dir
STATIC_DIR = Path(__file__).resolve().parent / "static"  # locates CODE, not data — OK to keep
SETTINGS.ensure_dirs()
```

  Resolution order is then: `SCOUTMB_DATA_DIR` (set by the launcher in production) → the
  stdlib OS data location → `cwd` **only** when `SCOUTMB_DEV` is explicitly set. This fixes
  the earlier `dev_mode = not SCOUTMB_DATA_DIR` heuristic, which made *every* env-less launch
  a `cwd` launch and never reached the OS location. Keep the `sys.path` insert for now
  (removed in Slice 2). The repo-root dev workflow runs with `SCOUTMB_DEV=1`.

- [ ] **Step 5: Run tests + smoke the app** (start it and actually hit `/api/status`)

```bash
uv sync --locked --all-extras && uv run pytest tests/unit/test_ui_settings.py -q
SCOUTMB_DEV=1 uv run python run_app.py --browser   # UI loads; GET /api/status returns 200; Ctrl-C
```

- [ ] **Step 6: Commit**

```bash
git add ui/server.py tests/unit/test_ui_settings.py
git commit -m "fix: resolve UI data paths explicitly, never from __file__ (Hazard 1)"
```

---

### Task 15: Copy-only legacy migration with SHA-256 verification

**Goal:** Migrate the one live install's data from `app/` to `data/` — copy, **SHA-256
verify**, mark; never move or delete; idempotent; collision-safe; leave an explanatory
old-root marker. Because this wires into the *live* `bootstrap/main.py`, the one real
dataset migrates hash-verified from the start. (Staging/resumability is Slice 3.)

**Files:**
- Create: `bootstrap/migrate.py`
- Modify: `bootstrap/paths.py` (add `data_dir`), `bootstrap/main.py` (call migration; export `SCOUTMB_DATA_DIR`)
- Test: `tests/unit/test_migrate.py`

**Acceptance Criteria:**
- [ ] Copies `scouts.csv`, `pdf-uploads/`, `runs/` from `app/` to `data/`
- [ ] Never deletes/moves originals; idempotent via `.migrated`
- [ ] **Every copied file is SHA-256-verified** against its source; the marker records `"verification": "sha256"`
- [ ] Collision writes `<name>.legacy`; a **second** collision writes `<name>.legacy-2` and
      **never deletes** the existing `.legacy`
- [ ] Old root gets an explanatory marker; launcher exports `SCOUTMB_DATA_DIR`

**Verify:** `uv run pytest tests/unit/test_migrate.py -q`

**Steps:**

- [ ] **Step 1: RED tests** — copies-all, originals-retained, idempotent, collision-writes-alongside, double-collision-never-deletes, no-legacy-is-noop, hash-verified. (Build a fake `app/{scouts.csv,pdf-uploads,runs/2026-.../summary.json}` in `tmp_path`.)

```python
# tests/unit/test_migrate.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bootstrap.migrate import MIGRATION_MARKER, migrate_legacy_data  # noqa: E402


def _legacy(root):
    app = root / "app"; data = root / "data"
    (app / "pdf-uploads").mkdir(parents=True)
    (app / "runs" / "2026-07-19_2139").mkdir(parents=True)
    (app / "scouts.csv").write_text("Attendee Name,QR Code Contents\n", encoding="utf-8")
    (app / "runs" / "2026-07-19_2139" / "summary.json").write_text("{}", encoding="utf-8")
    return app, data


def test_copies_all(tmp_path):
    app, data = _legacy(tmp_path); migrate_legacy_data(app, data)
    assert (data / "scouts.csv").is_file() and (data / "runs" / "2026-07-19_2139" / "summary.json").is_file()


def test_originals_retained(tmp_path):
    app, data = _legacy(tmp_path); migrate_legacy_data(app, data)
    assert (app / "scouts.csv").is_file()


def test_idempotent(tmp_path):
    app, data = _legacy(tmp_path); migrate_legacy_data(app, data)
    (data / "scouts.csv").write_text("edited", encoding="utf-8"); migrate_legacy_data(app, data)
    assert (data / "scouts.csv").read_text(encoding="utf-8") == "edited"
    assert (data / MIGRATION_MARKER).is_file()


def test_collision_writes_alongside(tmp_path):
    app, data = _legacy(tmp_path); data.mkdir(parents=True, exist_ok=True)
    (data / "scouts.csv").write_text("pre", encoding="utf-8"); migrate_legacy_data(app, data)
    assert (data / "scouts.csv").read_text(encoding="utf-8") == "pre"
    assert (data / "scouts.csv.legacy").read_text(encoding="utf-8").startswith("Attendee Name")


def test_double_collision_never_deletes_existing_legacy(tmp_path):
    """A second migration (marker removed) must not delete the first .legacy."""
    app, data = _legacy(tmp_path); data.mkdir(parents=True, exist_ok=True)
    (data / "scouts.csv").write_text("pre", encoding="utf-8")
    migrate_legacy_data(app, data)                       # -> scouts.csv.legacy
    (data / MIGRATION_MARKER).unlink()                   # simulate a re-run
    migrate_legacy_data(app, data)                       # -> scouts.csv.legacy-2
    assert (data / "scouts.csv.legacy").exists()         # first preserved copy survives
    assert (data / "scouts.csv.legacy-2").exists()       # second collision preserved separately


def test_no_legacy_is_noop(tmp_path):
    data = tmp_path / "data"; migrate_legacy_data(tmp_path / "app", data)
    assert not data.exists() or not any(data.iterdir())


def test_copies_are_hash_verified_and_recorded(tmp_path):
    import hashlib, json
    app, data = _legacy(tmp_path)
    report = migrate_legacy_data(app, data)
    assert report["verification"] == "sha256"
    src = (app / "scouts.csv").read_bytes()
    dst = (data / "scouts.csv").read_bytes()
    assert hashlib.sha256(src).hexdigest() == hashlib.sha256(dst).hexdigest()
    assert json.loads((data / MIGRATION_MARKER).read_text())["verification"] == "sha256"


def test_old_root_gets_an_explanatory_marker(tmp_path):
    app, data = _legacy(tmp_path)
    migrate_legacy_data(app, data)
    assert (app / "MOVED-README.txt").is_file()
```

Plus a small test that the launcher exports `SCOUTMB_DATA_DIR` (Step 4 wiring):

```python
# tests/unit/test_migrate.py  (continued)
import pytest


def test_launcher_exports_data_dir_env(monkeypatch, tmp_path):
    """_launch_app must put SCOUTMB_DATA_DIR in the child env so the app resolves data/."""
    # bootstrap.main -> bootstrap.webview2 -> `import winreg`, which only exists on Windows.
    # Run this on the Windows target; skip elsewhere (the winreg fix that lets bootstrap
    # import cross-platform is Slice 4).
    pytest.importorskip("winreg")
    monkeypatch.setenv("SCOUTMB_BOOTSTRAP_ROOT", str(tmp_path))
    import bootstrap.main as bmain

    captured = {}

    class _Popen:
        def __init__(self, *a, env=None, **k):
            captured["env"] = env or {}

    monkeypatch.setattr(bmain.subprocess, "Popen", _Popen)
    monkeypatch.setattr(bmain.time, "sleep", lambda *_: None)
    paths = bmain.get_paths()
    bmain._launch_app(paths, channel=None)
    assert captured["env"].get("SCOUTMB_DATA_DIR") == str(paths.data_dir)
```

- [ ] **Step 2: Run RED**, expect `ModuleNotFoundError: bootstrap.migrate`.

- [ ] **Step 3: Implement** (stdlib-only — `bootstrap/` cannot import `scoutmb`)

```python
# bootstrap/migrate.py
"""One-time COPY of legacy app/ user data into data/. Never moves or deletes.

One install exists with a season of real records. If this migration is wrong, the
data must still be where it always was. Every copied file is verified by SHA-256, not
just size — the data is irreplaceable, and hashing it is cheap. Staging, resumability,
and the marker-ordering contract are Slice 3 hardening; Slice 1 copies + hash-verifies.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

MIGRATION_MARKER = ".migrated"
_ITEMS = [("scouts.csv", False), ("pdf-uploads", True), ("runs", True)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_tree(src: Path, dst: Path) -> None:
    """Every file under src has a byte-identical (SHA-256) twin under dst."""
    src_files = sorted(p for p in src.rglob("*") if p.is_file())
    for src_file in src_files:
        dst_file = dst / src_file.relative_to(src)
        if not dst_file.is_file() or _sha256(src_file) != _sha256(dst_file):
            raise RuntimeError(f"migration hash verify failed for {src_file.relative_to(src)}")


def migrate_legacy_data(app_dir: Path, data_dir: Path) -> dict[str, object] | None:
    if (data_dir / MIGRATION_MARKER).is_file() or not app_dir.is_dir():
        return None
    present = [(n, d) for n, d in _ITEMS if (app_dir / n).exists()]
    if not present:
        return None
    data_dir.mkdir(parents=True, exist_ok=True)
    copied, collisions = [], []
    for name, is_dir in present:
        src = app_dir / name
        dst = data_dir / name
        if dst.exists():
            # Preserve every prior copy — NEVER delete an existing .legacy. Pick the first
            # free .legacy / .legacy-2 / .legacy-3 ... name instead.
            collisions.append(name)
            candidate = data_dir / f"{name}.legacy"
            suffix = 1
            while candidate.exists():
                suffix += 1
                candidate = data_dir / f"{name}.legacy-{suffix}"
            dst = candidate
        if is_dir:
            shutil.copytree(src, dst)
            _verify_tree(src, dst)
        else:
            shutil.copy2(src, dst)
            if _sha256(src) != _sha256(dst):
                raise RuntimeError(f"migration hash verify failed for {name}")
        copied.append(dst.name)
    # Write the old-root explanatory marker BEFORE the .migrated completion marker. If the
    # README write failed after .migrated existed, every rerun would return early (marker
    # present) and the old root would never get its notice. Completion marker is always last.
    (app_dir / "MOVED-README.txt").write_text(
        "This folder's data was copied to the app's data directory. Originals are "
        "retained here but no longer used. Do not run the old app from here.\n",
        encoding="utf-8")
    report = {"migrated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "source": str(app_dir), "copied": copied, "collisions": collisions,
              "verification": "sha256", "originals_retained": True}
    (data_dir / MIGRATION_MARKER).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
```

- [ ] **Step 4: Wire into bootstrap.** In `bootstrap/paths.py` add `data_dir: Path` to
  `AppPaths` (+ `ensure_dirs`, `data_dir=root / "data"` in `get_paths`). In
  `bootstrap/main.py._run`, after `source_sync.sync_app_source(paths)` call
  `migrate.migrate_legacy_data(paths.app_dir, paths.data_dir)` and log the report; in
  `_launch_app` add `"SCOUTMB_DATA_DIR": str(paths.data_dir)` to the child env.

- [ ] **Step 5: Run tests + rehearse on a throwaway root**

```bash
uv run pytest tests/unit/test_migrate.py -q
export WORK=$(mktemp -d); mkdir -p "$WORK/app/runs/x" "$WORK/app/pdf-uploads"
echo "Attendee Name,QR Code Contents" > "$WORK/app/scouts.csv"
uv run python -c "from pathlib import Path; from bootstrap.migrate import migrate_legacy_data as m; import os; r=Path(os.environ['WORK']); print(m(r/'app', r/'data')); print('original kept:', (r/'app'/'scouts.csv').is_file())"
```
Expected: report dict prints (with `"verification": "sha256"`); `original kept: True`.
The `WORK` assignment is **exported before** `uv run` so `os.environ['WORK']` resolves —
placing `WORK=…` after `python -c` would make it an argument, not an env var.

- [ ] **Step 6: Commit**

```bash
git add bootstrap/migrate.py bootstrap/paths.py bootstrap/main.py tests/unit/test_migrate.py
git commit -m "feat: copy-only legacy migration into data/, originals retained"
```

---

### Gate 1a — In-place correctness go/no-go

**Goal:** One reproducible offline run: tooling green, offline enforced, the **targeted**
characterization that guards each fix green (`requirement_path`, inference, `process_scout`,
CSV headers — Tasks 7–9), identity fixed, atomic writes in place, data-root explicit,
migration proven, privacy clean. The **exhaustive** Phase A matrix is Slice 1b's **Gate 1b**,
which is the one that precedes Slice 2.

**Verify (all must pass):**
```bash
uv sync --locked --all-extras
uv run ruff check . && uv run ruff format --check . && uv run mypy
SCOUTMB_DEV=1 uv run pytest -m "not live_service and not playwright" --cov=src/scoutmb --cov-branch -q
uv run python tools/check_private_data.py --corpus raw_data tests
uv run python tools/verify_corpus.py raw_data
```

**Expected GO:** every command exits 0; the targeted characterization (Tasks 7–9) is pinned;
two same-named attendees stay separate; no failed write truncates a prior file; migration
copies without touching originals (SHA-256 verified); `private-data findings: 0` (including
the corpus cross-reference); no non-loopback request.

**NO-GO:** stop, assign the failing evidence to its task, keep legacy behavior intact,
rerun the gate. Do **not** begin dependent work with a conditional waiver.

**Before Slice 2** (not before 1b): snapshot the one live installation's `app/` directory to
external storage. Migration is copy-only, SHA-256-verified, and tested, but one irreplaceable
dataset earns a manual backup.

**Then:** proceed to Slice 1b (full Phase A characterization). Gate 1b — not Gate 1a — is
what unblocks Slice 2, because Slice 2's parity tests need the complete oracle 1b builds.

---

## Self-review

**Reviewed by /codex three times (2026-07-22); split into 1a + 1b after the third.** Fixes
carried into 1a: the module-scope Playwright/openpyxl import that blocked characterization
(execution rule 6 + `--all-extras`); the `disable_socket` loopback break (Task 3); the
migration `.legacy` deletion (Task 15, now non-destructive + SHA-256) and marker ordering;
the full-UUID filename (Task 12); atomic routing of `errors.csv`/`missing_requirements.csv`
(Task 13); the `ruff`-on-`bootstrap` failure (Task 1 exclude); and the launcher-break — the
fix helpers now live in the flat scripts the launcher ships, not `src/scoutmb`. The
characterization-matrix findings (Tasks 16–19: PDF signatures, loader URLs, `parse_args`,
cancel-endpoint, `measure_baseline`, placeholders) moved with those tasks into **Slice 1b**,
where they are being completed.

**Spec coverage (1a), with honest scope:** D4 partial — pyproject/lock only, **not**
`requirements.txt`-derived-from-lock (that remainder is a later slice) (Task 1); CI (2,7);
D9/D27 offline — socket + app-policy layers only, **browser-subprocess egress + egress-denied
CI are Slice 2** (3); D7 synthetic fixtures + tripwire (4,5); D12 corpus (6); **targeted
characterization** guarding the fixes (7,8,9) — the **exhaustive D8 matrix is Slice 1b**;
**D3/D25 partial — grouping + filenames only, output-column scrub is Slice 2** (10,11,12);
**D11 partial — user-facing writers only, full atomic contract is Slice 2** (13); D6
data_root/Hazard-1 (14); **D5 — copy-only + SHA-256; staging/resumability is Slice 3** (15).

**Self-guarding, not full-matrix:** each in-place fix pins exactly the behavior it changes
(Task 13 asserts the header of every writer it routes; Task 14 smokes the read routes; Task
11 is guarded by Task 8's inference characterization). So 1a needs no dependency on 1b. 1b
builds the exhaustive oracle (all input formats, all output schemas, ScoutingEvent contract,
bootstrap/web/lifecycle, the request-count baseline) that Slice 2's parity tests consume.

**Deferred to Slice 2+ (by design):** hexagonal restructure, typed core beyond identity,
the ScoutingEvent **fake service** + gateway, run-state machine, structural web/`JobRegistry`
+ the 4 UI bugs, entrypoint parity, clean distributions, storage/retention, transactional
releases, installer/capabilities, diagnostics, performance **gate** (baseline captured
here), supply-chain license gate. Each lands in its slice.

**Known follow-ups carried forward:** the schedule-dedup rule (`:510`) is exercised only
indirectly here; it becomes a pure-function test when `payloads.py` is extracted in
Slice 2. `bootstrap/webview2.py`'s module-level `import winreg` still blocks importing the
`bootstrap` package on macOS; Task 15 imports `bootstrap.migrate` directly (no transitive
`winreg`), so it passes — the `winreg` fix is Slice 4.

**Type consistency:** `AttendeeId.parse`/`RunIdentity.output_id` (Task 10) are used in
Tasks 11–12; `attendee_filename_stem(name, output_id)` (Task 12) matches both call sites;
`build_missing_requirements` returns `{attendee_id: {"display_name", "badges"}}` from Task
11 and Task 12/`write_email_reports` read that shape.

**Placeholder scan:** no `...`/TODO/ellipsis test bodies remain in 1a (Tasks 1–15 carry
complete, runnable code). Characterization tests that pin an exact legacy value carry a
"correct the expectation from the observed run" note — inherent to characterization, not a
deferred TODO.

**Self-guard for Task 13 (post-split):** the writers Task 13 routes atomically are pinned by
Task 13's own tests plus Task 9's CSV-header characterization. `write_attendees_csv`'s 7-column
header (previously pinned by the moved Task 16) is now asserted directly inside Task 13 (it
changes that writer, so it pins it). No writer 1a touches goes unpinned.
