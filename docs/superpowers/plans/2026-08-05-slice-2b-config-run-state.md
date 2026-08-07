# Slice 2b.2 — Typed Configuration & Durable Run State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `argparse.Namespace` threading with one frozen `ScheduleConfig` dataclass shared
by the CLI and the local web UI (B6), and build a versioned run-state machine plus a
lifespan-owned job supervisor that retains every background task reference (B7) — as standalone,
independently-tested units. Wiring the supervisor into `ui/server.py`'s actual routes (replacing
the `busy` dict and today's unreferenced `asyncio.create_task(worker())` calls) is sub-plan 3
(B8), which also converts `ui/server.py` into the `create_app(settings)` factory this supervisor
needs a lifespan hook to attach to — that factory doesn't exist yet, so there is nothing to wire
into until then.

**Architecture:** `src/scoutmb/config.py` holds one frozen dataclass whose field defaults are the
single source of truth `scout_schedule_cli.parse_args()` reads its argparse defaults from.
`src/scoutmb/core/run_state.py` holds a total transition-table state machine with no I/O.
`src/scoutmb/runtime/jobs.py` holds a `JobSupervisor` that owns `asyncio.Task` references and
cancels+awaits all of them on shutdown — tested against a bare `asyncio` event loop, not FastAPI.

**Tech Stack:** Python 3.12, `dataclasses`, `enum.StrEnum`, `asyncio`, Hypothesis
(`hypothesis.strategies`), pytest.

**Global Constraints:**
- `ScheduleConfig`'s field names match the existing `argparse.Namespace` attribute names exactly
  (`input`, `sheet`, `output`, `headed`, `channel`, `timeout`, `request_delay_ms`,
  `scout_delay_ms`, `allow_dead_assets`, `include_adults`, `no_html`, `html_name`,
  `email_report`) — `tests/characterization/test_cli_sched_matrix.py` reads these off whatever
  `parse_args()` returns via plain attribute access, so an exact-name match is what keeps that
  characterization test green with zero edits.
- `process_scout`/`async_main` are never called with a keyword argument for their config
  parameter anywhere in the test suite (verified: `grep -rn "process_scout(\|async_main(" tests/
  | grep "args="` returns nothing) — safe to rename that parameter from `args` to `config`.
- No new dependency. Hypothesis is already a project dependency (used elsewhere for the DTO
  round-trip property per the Phase B spec).

**User decisions (already made):** Split slice 2b into four independent sub-plans by subsystem;
this sub-plan covers B6 (typed config) + B7 (run state / job supervisor) only, deliberately
stopping short of wiring the supervisor into `ui/server.py` (that's sub-plan 3, B8).

**Design decisions this sub-plan makes** (flagged for review before execution):

1. **`ScheduleConfig` lives in `src/scoutmb/config.py`**, a new module — the package layout table
   in the Phase B spec lists `config.py` under "2a" but it was never created in Slice 2a (verified:
   `find src -iname config.py` returns nothing on this branch); this sub-plan is where it actually
   lands.
2. **Run-state events model one run's lifecycle end to end** (`IDLE → RUNNING → {PAUSED,
   CANCELLING, COMPLETED, FAILED} → …`), not a resumable multi-run counter. A new run gets a new
   `RunStateMachine` instance; there is no legal transition out of a terminal state
   (`COMPLETED`/`FAILED`/`CANCELLED`) — matching "illegal transitions fail closed."
3. **`JobSupervisor.shutdown()` guarantees no `asyncio.Task` remains pending after it returns —
   it does not and cannot guarantee the underlying OS thread behind an `asyncio.to_thread` call
   has stopped running.** `asyncio.Task.cancel()` delivers `CancelledError` at the task's next
   await point; it has no mechanism to interrupt a thread already executing inside
   `run_in_executor`. This is a real Python-level limitation, not a design gap — stated explicitly
   because the Phase B spec's own methodology warns against exactly this kind of unverified claim
   about runtime behavior ("cancellation... leaves no pending task" is proven here; "leaves no
   running thread" is not claimed).

---

## Task B6: `ScheduleConfig` (+ `UiSettings`) replaces `Namespace` threading

**Goal:** One frozen `ScheduleConfig` dataclass, constructed by both `scout_schedule_cli.parse_args()`
and `ui/server.py`'s schedule-download worker, replaces the argparse `Namespace` both sites build
today. `email_report` gets an explicit default everywhere, so the `getattr(args, "email_report",
False)` defense in `async_main` can be deleted in the same change that removes the omission it
was defending against. `UiSettings` (the local web UI's data-root resolution, currently defined
inline in `ui/server.py`) also moves into this same module — see Design Decision below.

**Design decision:** `UiSettings` belongs in `src/scoutmb/config.py`, not a new sibling module
like `scoutmb.ui_settings`. The Phase B spec's allowed dependency-edge table names specific
layers (`interfaces`, `features`, `adapters`, `core`, `ports`, `runtime`, `config`, `errors`) —
a bare top-level `scoutmb.ui_settings` module fits none of them, which the architecture test's
layer-classification logic has no way to recognize. `config` is an explicitly named layer, and
`UiSettings` is exactly a configuration record, so it belongs alongside `ScheduleConfig` here
rather than inventing an unrecognized module the dependency-rule test would either silently
exempt or reject.

**Files:**
- Create: `src/scoutmb/config.py`
- Modify: `scout_schedule_cli.py` (`parse_args`, `process_scout`, `async_main` parameter rename
  and the `getattr` removal), `ui/server.py` (`start_schedule_download`'s worker, and its
  `UiSettings` class/`_platform_data_root` become a re-export from `scoutmb.config`)
- Test: `tests/unit/test_config.py`, `tests/contracts/test_cli_defaults_parity.py`

**Acceptance Criteria:**
- [ ] `ScheduleConfig`'s dataclass field defaults and `parse_args()`'s argparse defaults are the
      same thirteen values, sourced from one place — a changed default in one place changes both
- [ ] `parse_args()` returns a `ScheduleConfig`, not an `argparse.Namespace`
- [ ] `ui/server.py`'s schedule-download worker constructs a `ScheduleConfig` with
      `email_report=False` explicit — no field omitted
- [ ] `getattr(config, "email_report", False)` no longer appears in `async_main`
- [ ] `tests/characterization/test_cli_sched_matrix.py` passes unmodified
- [ ] `UiSettings` is importable from `scoutmb.config`; `ui/server.py`'s own class definition is
      replaced by a re-export, unchanged behavior (`tests/unit/test_ui_settings.py` needs its
      import updated — done here rather than left dangling for sub-plan 4 to discover, since the
      move happens in this task)

**Verify:** `uv run pytest tests/unit/test_config.py tests/contracts/test_cli_defaults_parity.py tests/characterization/test_cli_sched_matrix.py -q` → PASS

**Recovery:** Revert `parse_args`/`ui/server.py` to construct `argparse.Namespace` directly; keep
`ScheduleConfig` merged but unreferenced.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_config.py
"""B6: ScheduleConfig's field defaults are the single source of truth CLI argparse defaults
must agree with -- this test pins the THIRTEEN values themselves so a drift in either place
is caught here, independent of parse_args()."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scoutmb.config import ScheduleConfig


def test_defaults_match_the_documented_cli_defaults() -> None:
    config = ScheduleConfig(input=Path("scouts.csv"))
    assert config.sheet == "Scouts Only"
    assert config.output == Path("scouting-output")
    assert config.headed is False
    assert config.channel is None
    assert config.timeout == 45
    assert config.request_delay_ms == 200
    assert config.scout_delay_ms is None
    assert config.allow_dead_assets is False
    assert config.include_adults is False
    assert config.no_html is False
    assert config.html_name == "report.html"
    assert config.email_report is False


def test_is_frozen() -> None:
    config = ScheduleConfig(input=Path("scouts.csv"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.timeout = 99  # type: ignore[misc]
```

```python
# tests/contracts/test_cli_defaults_parity.py
"""CLI-SCHED-*: the argparse defaults parse_args() actually builds must equal ScheduleConfig's
own field defaults -- not merely "the same numbers typed twice", but READ FROM THE SAME PLACE, so
a future edit to one cannot silently diverge from the other."""

from __future__ import annotations

import dataclasses
import sys

import pytest

import scout_schedule_cli as cli
from scoutmb.config import ScheduleConfig


def test_parse_args_defaults_equal_scheduleconfig_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["scout_schedule_cli.py", "--input", "scouts.csv"])
    parsed = cli.parse_args()
    defaults = ScheduleConfig(input=parsed.input)

    for field in dataclasses.fields(ScheduleConfig):
        if field.name == "input":
            continue
        assert getattr(parsed, field.name) == getattr(defaults, field.name), field.name
```

Run: `uv run pytest tests/unit/test_config.py tests/contracts/test_cli_defaults_parity.py -v` → FAIL (`scoutmb.config` doesn't exist)

- [ ] **Step 2: Write `ScheduleConfig` and `UiSettings`**

```python
# src/scoutmb/config.py
"""Frozen configuration (D6). ScheduleConfig replaces argparse.Namespace threading through
process_scout/async_main; both the CLI's argparse defaults and the local web UI's hand-built
config read their non-required field values from THIS module's dataclass defaults, so the two
call sites cannot drift apart the way a Namespace built by hand in two places already has
(ui.server's worker omits email_report; async_main's getattr(..., False) compensated for that
omission -- both go together in this task).

UiSettings (the local web UI's data-root resolution) lives here too, unchanged from its current
ui/server.py definition -- moved rather than duplicated, since `config` is a recognized layer in
the Phase B spec's dependency-edge table and a new sibling module would not be."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ScoutingMeritBadges"
DATA_DIR_ENV = "SCOUTMB_DATA_DIR"


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    input: Path
    sheet: str = "Scouts Only"
    output: Path = Path("scouting-output")
    headed: bool = False
    channel: str | None = None
    timeout: int = 45
    request_delay_ms: int = 200
    scout_delay_ms: int | None = None
    allow_dead_assets: bool = False
    include_adults: bool = False
    no_html: bool = False
    html_name: str = "report.html"
    email_report: bool = False


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
    """Where the local web UI reads/writes user data. NEVER derive a data path from __file__ --
    that ties irreplaceable data to the code's on-disk location, so moving or reinstalling
    silently relocates or destroys it."""

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

- [ ] **Step 3: Re-point `ui/server.py` at the moved `UiSettings`, and fix `tests/unit/test_ui_settings.py`'s import**

```python
# ui/server.py -- replace the class UiSettings / _platform_data_root block (currently lines
# 40-79) with a re-export; the module-level SETTINGS = UiSettings.resolve(...) construction and
# its import-time side effect are UNCHANGED (ui/server.py is not what UI-IMPORT-001 targets)
from scoutmb.config import APP_NAME, DATA_DIR_ENV, UiSettings  # noqa: F401 - legacy public surface
```

```python
# tests/unit/test_ui_settings.py -- update the one import line
from scoutmb.config import UiSettings
```

- [ ] **Step 4: Re-point `parse_args()` at `ScheduleConfig`'s defaults**

```python
# scout_schedule_cli.py -- replace parse_args (lines 93-183)
from scoutmb.config import ScheduleConfig

# Sourced once, here: every non-required argparse default below reads this instance rather than
# repeating a literal, so ScheduleConfig's own field defaults are the single source of truth
# tests/contracts/test_cli_defaults_parity.py checks against.
_DEFAULTS = ScheduleConfig(input=Path("unused"))


def parse_args() -> ScheduleConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Pull schedules and class requirements from ScoutingEvent QR URLs, "
            "bypassing the site's broken jQuery Mobile rendering."
        )
    )
    parser.add_argument("--input", "-i", required=True, type=Path, help=(
        "CSV, XLSX, JSON, or text file containing scout names and QR URLs."
    ))
    parser.add_argument("--sheet", default=_DEFAULTS.sheet, help=(
        f'XLSX sheet name (default: "{_DEFAULTS.sheet}").'
    ))
    parser.add_argument("--output", "-o", type=Path, default=_DEFAULTS.output, help=(
        f"Output directory (default: {_DEFAULTS.output})."
    ))
    parser.add_argument("--headed", action="store_true", help="Show the Chromium window while running.")
    parser.add_argument("--channel", default=_DEFAULTS.channel, help=(
        "Playwright browser channel to use (e.g. 'msedge'); default uses Playwright's bundled Chromium."
    ))
    parser.add_argument("--timeout", type=int, default=_DEFAULTS.timeout, help=(
        f"Seconds to wait for the schedule response for each scout (default: {_DEFAULTS.timeout})."
    ))
    parser.add_argument("--request-delay-ms", type=int, default=_DEFAULTS.request_delay_ms, help=(
        f"Delay between class-requirement requests (default: {_DEFAULTS.request_delay_ms} ms)."
    ))
    parser.add_argument("--scout-delay-ms", type=int, default=_DEFAULTS.scout_delay_ms, help=(
        "Delay between scouts, in milliseconds. Default: a random delay "
        "between 500-2000 ms per scout (so requests don't hit the server at a "
        "fixed cadence); pass a fixed value (e.g. 0 to disable, or 750 for a "
        "fixed 750ms) to override."
    ))
    parser.add_argument("--allow-dead-assets", action="store_true", help=(
        "Do not block the two known mike.dev.* JavaScript URLs that currently time out."
    ))
    parser.add_argument("--include-adults", action="store_true", help=(
        "Include Adult and Part-Time Adult rows when the input contains a Registrant Type column."
    ))
    parser.add_argument("--no-html", action="store_true", help=(
        "Do not generate the self-contained sortable/filterable HTML report."
    ))
    parser.add_argument("--html-name", default=_DEFAULTS.html_name, help=(
        f"HTML report filename inside the output directory (default: {_DEFAULTS.html_name})."
    ))
    parser.add_argument("--email-report", action="store_true", help=(
        "Also generate per-scout missing-requirement emails (HTML, text, and a "
        "combined CSV) in an 'emails' subdirectory of the output directory. "
        "The HTML report's 'Generate missing-requirement emails' button does "
        "this on demand when run through the local web UI, so this flag is "
        "only needed for bare command-line runs (default: off)."
    ))
    args = parser.parse_args()
    return ScheduleConfig(
        input=args.input,
        sheet=args.sheet,
        output=args.output,
        headed=args.headed,
        channel=args.channel,
        timeout=args.timeout,
        request_delay_ms=args.request_delay_ms,
        scout_delay_ms=args.scout_delay_ms,
        allow_dead_assets=args.allow_dead_assets,
        include_adults=args.include_adults,
        no_html=args.no_html,
        html_name=args.html_name,
        email_report=args.email_report,
    )
```

- [ ] **Step 5: Rename `process_scout`/`async_main`'s parameter and remove the `getattr` defense**

```python
# scout_schedule_cli.py -- process_scout's signature (was: args: argparse.Namespace)
async def process_scout(
    browser: Browser,
    scout: ScoutInput,
    config: ScheduleConfig,
    raw_dir: Path,
    run_identity: RunIdentity | None = None,
) -> ScoutResult:
```

Every reference to `args.` inside `process_scout`'s body (already rewritten to accumulate
locally in sub-plan 1's Task B5.1) becomes `config.` — same attribute names, so this is a pure
rename, not a logic change.

```python
# scout_schedule_cli.py -- async_main's signature and its two args.* reads
async def async_main(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    scouts = load_inputs(config.input, config.sheet, config.include_adults)
    config.output.mkdir(parents=True, exist_ok=True)
    raw_dir = config.output / "raw"
    ...
    result = await process_scout(browser, scout, config, raw_dir, run_identity)
    ...
    write_outputs(
        config.output,
        results,
        generate_html=not config.no_html,
        html_name=config.html_name,
        generate_email_report=config.email_report,  # was: getattr(args, "email_report", False)
        run_identity=run_identity,
    )
```

```python
# scout_schedule_cli.py -- main() passes parse_args()'s ScheduleConfig straight through, no change needed
def main() -> int:
    config = parse_args()
    try:
        return asyncio.run(async_main(config))
    ...
```

- [ ] **Step 6: Update `ui/server.py`'s worker**

```python
# ui/server.py -- start_schedule_download's worker, replace the Namespace(...) construction
from scoutmb.config import ScheduleConfig  # replaces: from argparse import Namespace

...

async def worker() -> None:
    try:
        config = ScheduleConfig(
            input=SCOUTS_CSV,
            sheet="Scouts Only",
            output=run_dir,
            headed=False,
            timeout=45,
            request_delay_ms=200,
            scout_delay_ms=None,
            allow_dead_assets=False,
            include_adults=False,
            no_html=False,
            html_name="report.html",
            channel=BROWSER_CHANNEL,
            email_report=False,  # explicit now -- this is the field the getattr used to cover for
        )
        await scout_schedule_cli.async_main(
            config, progress_callback=on_progress, resume_event=resume_event
        )
        ...
```

Remove the now-unused `from argparse import Namespace` import at the top of `ui/server.py`.

- [ ] **Step 7: Run and commit**

```bash
uv run pytest -q
```

```bash
git add src/scoutmb/config.py scout_schedule_cli.py ui/server.py tests/unit/test_config.py tests/unit/test_ui_settings.py tests/contracts/test_cli_defaults_parity.py
git commit -m "refactor(config): ScheduleConfig+UiSettings replace argparse.Namespace and ui/server.py's inline class"
```

---

## Task B7.1: `core/run_state.py` — versioned run-state machine

**Goal:** A total transition table over `RunState`/`RunEvent`: every `(state, event)` pair either
transitions or raises `IllegalTransition`, proven by a Hypothesis property, not just the
explicitly-listed edges.

**Files:**
- Create: `src/scoutmb/core/run_state.py`
- Test: `tests/unit/jobs/test_run_state.py`

**Acceptance Criteria:**
- [ ] `RunStateMachine().apply(RunEvent.START)` transitions `IDLE → RUNNING`
- [ ] Every explicitly-illegal edge in the test (e.g. `PAUSE` from `IDLE`) raises `IllegalTransition`
      and leaves `.state` unchanged
- [ ] A Hypothesis property over the full `RunState x RunEvent` Cartesian product proves every
      pair either transitions or raises — no pair silently no-ops or raises something else
- [ ] No terminal state (`COMPLETED`/`FAILED`/`CANCELLED`) has any legal outgoing transition

**Verify:** `uv run pytest tests/unit/jobs/test_run_state.py -q` → PASS

**Recovery:** Leave `RunStateMachine` unreferenced; `ui/server.py`'s `busy` dict stays the live
mechanism until sub-plan 3 wires the replacement in.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/jobs/test_run_state.py
"""B7: the run-state transition table is TOTAL -- every (state, event) pair either transitions
or fails closed via IllegalTransition, with no pair falling through to anything else (a silent
no-op, an unrelated exception, or a state left in an inconsistent partial-write)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scoutmb.core.run_state import IllegalTransition, RunEvent, RunState, RunStateMachine

_TERMINAL = {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}


def test_start_transitions_idle_to_running() -> None:
    machine = RunStateMachine()
    assert machine.state is RunState.IDLE
    assert machine.apply(RunEvent.START) is RunState.RUNNING
    assert machine.state is RunState.RUNNING


def test_pause_then_resume_round_trips() -> None:
    machine = RunStateMachine()
    machine.apply(RunEvent.START)
    assert machine.apply(RunEvent.PAUSE) is RunState.PAUSED
    assert machine.apply(RunEvent.RESUME) is RunState.RUNNING


def test_illegal_edge_raises_and_state_is_unchanged() -> None:
    machine = RunStateMachine()
    with pytest.raises(IllegalTransition) as exc_info:
        machine.apply(RunEvent.PAUSE)  # PAUSE is illegal from IDLE
    assert exc_info.value.state is RunState.IDLE
    assert exc_info.value.event is RunEvent.PAUSE
    assert machine.state is RunState.IDLE  # unchanged after the failed attempt


@pytest.mark.parametrize("terminal", sorted(_TERMINAL, key=lambda s: s.value))
def test_terminal_states_accept_no_further_event(terminal: RunState) -> None:
    machine = RunStateMachine(state=terminal)
    for event in RunEvent:
        with pytest.raises(IllegalTransition):
            machine.apply(event)
        assert machine.state is terminal  # every attempt fails closed, none mutate .state


@given(state=st.sampled_from(RunState), event=st.sampled_from(RunEvent))
def test_every_state_event_pair_transitions_or_fails_closed(
    state: RunState, event: RunEvent
) -> None:
    """Totality: NOTHING falls through. Either apply() returns a RunState (a legal edge) or it
    raises IllegalTransition -- there is no third outcome."""
    machine = RunStateMachine(state=state)
    try:
        result = machine.apply(event)
    except IllegalTransition as exc:
        assert exc.state is state
        assert exc.event is event
    else:
        assert isinstance(result, RunState)
        assert machine.state is result


# The Hypothesis property above proves TOTALITY (every pair transitions or raises -- no third
# outcome) but does NOT pin which SPECIFIC edges are legal: an implementation with a completely
# different (but still total) transition table would pass it too. This exhaustive parametrized
# test is the complement -- it enumerates the CURRENT _TRANSITIONS table and asserts each entry
# transitions to exactly its declared next-state, and separately asserts every (state, event)
# pair NOT in the table raises. Import _TRANSITIONS directly rather than re-deriving the pairs by
# hand, so this test can never drift from the table it is meant to pin.
_ALL_PAIRS = [(state, event) for state in RunState for event in RunEvent]


@pytest.mark.parametrize(("state", "event"), _ALL_PAIRS)
def test_transition_table_matches_exactly(state: RunState, event: RunEvent) -> None:
    from scoutmb.core.run_state import _TRANSITIONS

    machine = RunStateMachine(state=state)
    expected_next = _TRANSITIONS.get((state, event))

    if expected_next is None:
        with pytest.raises(IllegalTransition):
            machine.apply(event)
        assert machine.state is state
    else:
        assert machine.apply(event) == expected_next
        assert machine.state == expected_next
```

Run: `uv run pytest tests/unit/jobs/test_run_state.py -v` → FAIL (module doesn't exist)

- [ ] **Step 2: Implement the state machine**

```python
# src/scoutmb/core/run_state.py
"""A versioned, total run-state machine (D33). Models ONE run's lifecycle from IDLE to a
terminal state; a new run gets a new RunStateMachine instance rather than reusing a terminal one.
Every (state, event) pair not explicitly listed in _TRANSITIONS raises IllegalTransition -- proven
total by tests/unit/jobs/test_run_state.py's Hypothesis property, not merely asserted here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from scoutmb.errors import ScoutmbError

RUN_STATE_VERSION = 1


class RunState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunEvent(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    CANCELLED = "cancelled"
    COMPLETE = "complete"
    FAIL = "fail"


class IllegalTransition(ScoutmbError):
    """The event is not legal from the current state. Fails closed: the state machine's
    .state is never mutated by a rejected attempt."""

    def __init__(self, state: RunState, event: RunEvent) -> None:
        self.state = state
        self.event = event
        super().__init__(f"cannot apply {event.value!r} while in state {state.value!r}")


_TRANSITIONS: dict[tuple[RunState, RunEvent], RunState] = {
    (RunState.IDLE, RunEvent.START): RunState.RUNNING,
    (RunState.RUNNING, RunEvent.PAUSE): RunState.PAUSED,
    (RunState.PAUSED, RunEvent.RESUME): RunState.RUNNING,
    (RunState.RUNNING, RunEvent.CANCEL): RunState.CANCELLING,
    (RunState.PAUSED, RunEvent.CANCEL): RunState.CANCELLING,
    (RunState.CANCELLING, RunEvent.CANCELLED): RunState.CANCELLED,
    (RunState.RUNNING, RunEvent.COMPLETE): RunState.COMPLETED,
    (RunState.RUNNING, RunEvent.FAIL): RunState.FAILED,
    (RunState.PAUSED, RunEvent.FAIL): RunState.FAILED,
    (RunState.CANCELLING, RunEvent.FAIL): RunState.FAILED,
}


@dataclass(slots=True)
class RunStateMachine:
    state: RunState = RunState.IDLE
    version: int = RUN_STATE_VERSION

    def apply(self, event: RunEvent) -> RunState:
        key = (self.state, event)
        next_state = _TRANSITIONS.get(key)
        if next_state is None:
            raise IllegalTransition(self.state, event)
        self.state = next_state
        return next_state
```

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/unit/jobs/test_run_state.py -q
```

```bash
git add src/scoutmb/core/run_state.py tests/unit/jobs/test_run_state.py
git commit -m "feat(runtime): add versioned, total run-state machine"
```

---

## Task B7.2: `runtime/jobs.py` — lifespan-owned job supervisor

**Goal:** A `JobSupervisor` that retains a reference to every `asyncio.Task` it starts (fixing
the GC hazard in `ui/server.py`'s unreferenced `asyncio.create_task(worker())` calls) and, on
`shutdown()`, cancels and awaits all of them — including work dispatched through
`asyncio.to_thread`, up to the limit that Python's own cancellation model allows (see this
sub-plan's Design Decision 3).

**Files:**
- Create: `src/scoutmb/runtime/__init__.py`, `src/scoutmb/runtime/jobs.py`
- Test: `tests/integration/test_job_supervisor.py`

**Acceptance Criteria:**
- [ ] A task started via `JobSupervisor.start(job_id, coro)` is retained until it finishes, then
      removed from the registry automatically (via `add_done_callback`) — no manual cleanup call
      required for the success path
- [ ] `shutdown()` cancels every still-running task and awaits all of them; after it returns, the
      registry is empty and no task object reports `pending`
- [ ] Cancelling a task that is itself awaiting `asyncio.to_thread(...)` still leaves the
      supervisor's bookkeeping clean (no pending `asyncio.Task`) even though the underlying
      thread may still be finishing its blocking call — asserted precisely, not overclaimed
- [ ] `shutdown()` is idempotent — calling it twice does not raise

**Verify:** `uv run pytest tests/integration/test_job_supervisor.py -q` → PASS

**Recovery:** Leave `JobSupervisor` unreferenced; `ui/server.py`'s `busy` dict and bare
`asyncio.create_task` calls stay the live mechanism until sub-plan 3.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_job_supervisor.py
"""B7: JobSupervisor retains every task it starts and shutdown() cancels+awaits all of them,
including asyncio.to_thread work -- to the precise extent asyncio's own cancellation model
allows (see the sub-plan's Design Decision 3: cancelling a Task awaiting to_thread stops
AWAITING it, it cannot forcibly stop the underlying OS thread)."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from scoutmb.runtime.jobs import JobSupervisor


async def test_completed_task_is_retained_then_auto_removed() -> None:
    supervisor = JobSupervisor()

    async def quick() -> str:
        return "done"

    task = supervisor.start("job-1", quick())
    assert supervisor.get("job-1") is task
    result = await task
    assert result == "done"
    # add_done_callback fires on the same loop iteration the awaited task completes in, but
    # callbacks run via call_soon -- yield once so it has actually run before asserting.
    await asyncio.sleep(0)
    assert supervisor.get("job-1") is None


async def test_shutdown_cancels_and_awaits_all_running_tasks() -> None:
    supervisor = JobSupervisor()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_running() -> None:
        started.set()
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    supervisor.start("job-1", long_running())
    await started.wait()

    await supervisor.shutdown()

    assert cancelled.is_set()
    assert supervisor.get("job-1") is None
    assert supervisor.pending_count == 0


async def test_shutdown_is_idempotent() -> None:
    supervisor = JobSupervisor()
    await supervisor.shutdown()
    await supervisor.shutdown()  # must not raise


async def test_cancellation_during_a_blocking_adapter_call_leaves_no_pending_task() -> None:
    """Precise claim: after shutdown(), no asyncio.Task is pending. NOT claimed: the underlying
    thread has stopped -- asyncio.Task.cancel() cannot interrupt a thread already running inside
    run_in_executor, so this test uses a short, self-terminating blocking call rather than
    asserting on the thread's own lifetime."""
    supervisor = JobSupervisor()
    thread_finished = threading.Event()

    def blocking_work() -> None:
        time.sleep(0.05)
        thread_finished.set()

    async def wraps_thread() -> None:
        await asyncio.to_thread(blocking_work)

    task = supervisor.start("job-1", wraps_thread())
    await asyncio.sleep(0)  # let the task start and enter asyncio.to_thread

    await supervisor.shutdown()

    assert supervisor.pending_count == 0
    assert task.done()
    # The thread itself is short-lived and self-terminating by design (0.05s sleep) -- this
    # proves the supervisor's bookkeeping is clean, not that cancellation stopped the thread.
    thread_finished.wait(timeout=1.0)
    assert thread_finished.is_set()


async def test_reusing_a_job_id_before_the_first_task_finishes_does_not_lose_the_second() -> None:
    """A naive `self._tasks[job_id] = task` plus an unconditional pop in the done-callback has a
    real bug: if job A (id="x") is still running when job B (also id="x") starts, A's own
    done-callback later pops "x" unconditionally -- evicting B's task reference even though B is
    still running. The registry must only remove an entry if it is STILL the task that callback
    belongs to."""
    supervisor = JobSupervisor()
    first_may_finish = asyncio.Event()

    async def first() -> str:
        await first_may_finish.wait()
        return "first"

    async def second() -> str:
        await asyncio.sleep(0.05)
        return "second"

    first_task = supervisor.start("x", first())
    second_task = supervisor.start("x", second())  # reuses "x" while first_task is still running
    assert supervisor.get("x") is second_task  # the registry now tracks the newer task

    first_may_finish.set()
    await first_task  # first's done-callback fires now -- it must NOT evict second_task
    await asyncio.sleep(0)  # let the done-callback actually run

    assert supervisor.get("x") is second_task, "first's completion evicted second's still-live entry"
    await second_task
```

Run: `uv run pytest tests/integration/test_job_supervisor.py -v` → FAIL (module doesn't exist)

- [ ] **Step 2: Implement `JobSupervisor`**

```python
# src/scoutmb/runtime/__init__.py
```

```python
# src/scoutmb/runtime/jobs.py
"""Lifespan-owned job supervisor (D33). Retains a reference to every asyncio.Task it starts --
the bug this fixes is ui/server.py's bare `asyncio.create_task(worker())` with no retained
reference, which the event loop is free to garbage-collect mid-flight once the enclosing route
handler returns, silently abandoning in-flight work. shutdown() cancels and awaits every tracked
task so nothing outlives the app's lifespan.

Limitation, stated rather than glossed over: cancelling a Task awaiting asyncio.to_thread(...)
delivers CancelledError at the next await point in the ASYNC side; it cannot interrupt the
underlying OS thread already running inside the executor. "No pending task after shutdown" is
what this class guarantees -- "no thread still running" is not achievable through this
mechanism and is not claimed.

Duplicate job IDs: reusing a job_id while its previous task is still running is handled safely --
the done-callback only removes ITS OWN task from the registry if that task is still the current
occupant of that key, never unconditionally. Without that check, an older task's completion could
evict a newer task's still-live registry entry (a real bug an earlier draft of this class had)."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JobSupervisor:
    _tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)

    def start(self, job_id: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._tasks[job_id] = task
        task.add_done_callback(lambda finished, key=job_id: self._discard_if_current(key, finished))
        return task

    def _discard_if_current(self, job_id: str, finished_task: asyncio.Task[Any]) -> None:
        """Only remove job_id's registry entry if `finished_task` IS the task currently stored
        there -- a done-callback belonging to a SUPERSEDED task (job_id was reused before this
        one finished) must not evict whatever newer task now occupies that key."""
        if self._tasks.get(job_id) is finished_task:
            del self._tasks[job_id]

    def get(self, job_id: str) -> asyncio.Task[Any] | None:
        return self._tasks.get(job_id)

    @property
    def pending_count(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
```

> `add_done_callback`'s removal runs on a normal (non-cancelled) completion too, which is what
> makes `test_completed_task_is_retained_then_auto_removed` pass without an explicit `shutdown()`
> call — the registry only holds tasks that are genuinely still in flight. `asyncio.create_task`
> (not `asyncio.ensure_future`) is used deliberately: `start()`'s parameter is typed as a
> `Coroutine`, never an existing `Future`/`Task`, so `create_task` is the precise call for what
> this method actually accepts — `ensure_future`'s broader "coroutine or already-a-future" handling
> buys nothing here and reads as though a Task might be passed in, which the type hint already
> rules out.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/integration/test_job_supervisor.py -q
```

```bash
git add src/scoutmb/runtime tests/integration/test_job_supervisor.py
git commit -m "feat(runtime): add JobSupervisor retaining and cancelling all owned tasks on shutdown"
```

---

## Sub-plan gate (feeds Gate 2)

- `ScheduleConfig` is the sole config-threading mechanism through `parse_args`/`process_scout`/
  `async_main`/`ui/server.py`'s worker; no `argparse.Namespace` construction remains outside
  `parse_args()`'s own argparse call, and no `getattr(..., "email_report", False)` defense remains.
- `UiSettings` lives in `scoutmb.config` (a recognized dependency-edge-table layer), not a new
  unrecognized top-level module; `ui/server.py` and `tests/unit/test_ui_settings.py` both import
  it from there.
- `tests/characterization/test_cli_sched_matrix.py` passes unmodified.
- The run-state transition table is proven total by a Hypothesis property AND matches its exact
  intended shape by an exhaustive parametrized test over every `(state, event)` pair — totality
  alone would pass for a wrongly-shaped-but-still-total table.
- `JobSupervisor.shutdown()` leaves zero pending tasks, including ones that were awaiting
  `asyncio.to_thread`, proven by an integration test against a bare event loop; reusing a job ID
  before its predecessor finishes never loses the newer task's registry entry.
- Neither `RunStateMachine` nor `JobSupervisor` is wired into `ui/server.py` yet — that is
  sub-plan 3's job, once `create_app(settings)` exists to own a lifespan.
- `uv run pytest -q` green with no regressions.

**NO-GO:** Revert `parse_args`/`ui/server.py` to `Namespace` construction; keep `config.py`,
`run_state.py`, and `runtime/jobs.py` merged but unreferenced; return the specific failing
behavior to its task.
