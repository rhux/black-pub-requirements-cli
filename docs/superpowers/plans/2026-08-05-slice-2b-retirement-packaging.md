# Slice 2b.4 — Flat-Module Retirement & Release Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Revision note (post-Codex review):** An earlier draft of Task B10.2 rebuilt the circuit
> breaker fresh inside `process_scout` on every call, making `ACQ-BREAKER-*`'s cross-scout premise
> permanently unsatisfiable, and never touched the checkpoint store at all despite sub-plan 1
> reclassifying `ACQ-RESUME-*` as if it were composed. It also recorded every exception —
> including a real `KeyboardInterrupt`/cancellation — as `RunEvent.FAIL`, and applied
> `RunEvent.COMPLETE` before the report had actually been generated. Task B10.2 is rewritten
> around a new `features/acquisition/pipeline.py` that fixes all four, and is now also what
> `interfaces/cli/schedule.py` (`troop349-schedule`, sub-plan 3) calls directly — an independent
> review separately found that file still imported `scout_schedule_cli.async_main`, which this
> sub-plan's own B10.4 then deletes with nothing repointed. Also fixed: three test files
> (`tests/factories/records.py`, `tests/vertical/test_legacy_flows.py`,
> `tests/performance/test_phase_a_baseline.py`) the original file list missed entirely despite
> importing the flat modules directly; `ui/server.py`+`run_app.py`'s deletion split into two
> actually-separate commits to match this plan's own one-module-per-commit rule; and every
> `scoutmb.ui_settings` reference corrected to `scoutmb.config` (sub-plan 2).

**Goal:** Finish the cutover the first three sub-plans built additively (route production code
at the package), retire all four flat modules and their legacy characterization harnesses, and
ship a release root that installs and starts with no repository present.

**Architecture:** Sub-plans 1-3 built package equivalents (`AcquisitionService`, `RunStateMachine`,
`JobSupervisor`, `create_app`, three console scripts) proven by parity tests, without ever making
`scout_schedule_cli.py`/`ui/server.py` actually delegate to them in production. This sub-plan does
that wiring, proves each retiring module is pure delegation via the shape-check machinery, deletes
the flat modules and the legacy harnesses that drove them (in per-module commits, since retirement
is irreversible), then wires `bootstrap/` to sync the package instead of four loose files.

**Tech Stack:** The same stack as sub-plans 1-3 (nothing new); `PyInstaller`'s `build.spec` /
`bootstrap/source_sync.py` for the release-root packaging mechanics.

**Global Constraints:**
- `scout_schedule_cli.py` and `pdf_to_scouts.py` — the two modules other code still calls by
  name — are each added to `SHIMMED_MODULES` and proven pure delegation (via
  `test_shimmed_module_contains_no_business_logic`) **before** their deletion commits.
  `ui/server.py`/`run_app.py` are the stated exception (Design Decision 2 below) — nothing
  outside their own now-also-deleted test harness calls them for behavior, so shimming them
  first would prove a shape check nothing is left to observe a moment later.
- Retirement happens **one module per commit** — the spec calls this "the one genuinely
  irreversible step in Phase B," so each deletion is independently revertable. This applies
  literally to all four modules, including `run_app.py`/`ui/`, which Task B10.3 deletes as two
  separate commits despite landing in the same task.
- `bootstrap/build.spec`'s `datas` and `bootstrap/source_sync.py`'s `_FILES`/`_DIRS` are updated
  in the **same task** that deletes the flat files they currently reference — leaving either
  pointing at a deleted file breaks the release-root build silently.

**User decisions (already made):** Split slice 2b into four independent sub-plans by subsystem;
this sub-plan covers B10 (retirement) + B11 (release packaging) and depends on sub-plans 1-3
having merged first.

**Design decisions this sub-plan makes** (flagged for review before execution):

1. **A gap in sub-plan 3 is fixed here first (Task B10.0), not silently patched into that file.**
   `create_app` (built in sub-plan 3, Task B8.1/B8.3) never mounts static assets —
   `ui/server.py`'s `app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), ...)` has no
   package-side equivalent, so the release root would ship a server that answers `/api/*` but
   serves nothing at `/`. This must land before Task B10.3 deletes `ui/server.py`, or the local
   web UI's frontend disappears entirely.
2. **`ui/server.py`/`run_app.py` are deleted directly, without an intermediate shim state** —
   unlike `scout_schedule_cli.py`/`pdf_to_scouts.py`, nothing outside their own now-also-deleted
   test harness imports them for their *behavior* (only for `ui.server.busy`-style module-global
   introspection, which the legacy harness's own deletion removes in the same commit). Shimming
   them first would prove a shape check nothing is left to observe a moment later. The two CLI
   flat scripts get the full shim-then-shape-check-then-delete treatment because
   `tests/characterization/test_acquisition_matrix.py` etc. call their functions directly and by
   name, so "pure delegation" is a real, checkable intermediate state for them.
3. **The full CLI batch orchestration moves into a new package module
   (`features/acquisition/pipeline.py`, Task B10.2), not just `scout_schedule_cli.async_main`'s
   body.** `JobSupervisor` is deliberately not used here — it is a single-process CLI batch loop
   with no background tasks to retain, not a served app; force-fitting it in would add nothing.
   `RunStateMachine` **is** used, and for a real reason beyond "prove it's reused": it is what
   lets `RunEvent.COMPLETE` be withheld until reporting also succeeds (not just acquisition) and
   lets a real `KeyboardInterrupt`/`CancelledError` be recorded as `CANCEL`/`CANCELLED` rather
   than conflated with an ordinary `FAIL`. The orchestration lives in the package specifically
   because `interfaces/cli/schedule.py` (`troop349-schedule`, built in sub-plan 3) must call it
   directly, without importing `scout_schedule_cli` — which Task B10.4 deletes.

---

## Task B10.0: Mount static assets from the package (fixes a sub-plan 3 gap)

**Goal:** `create_app` serves `ui/static`'s frontend from a package resource location, so
`ui/server.py` can be deleted later in this sub-plan without breaking the local web UI.

**Files:**
- Move: `ui/static/*` → `src/scoutmb/resources/web_static/*`
- Modify: `src/scoutmb/interfaces/web/app.py` (mount both static roots)
- Test: `tests/parity/test_local_web_parity.py` (extend: `GET /` serves the frontend)

**Acceptance Criteria:**
- [ ] `GET /` on the package app returns the same `index.html` content `ui/server.py` serves
- [ ] Static assets are read via `importlib.resources`, never a `__file__`-derived path (the
      flat prohibition `tests/architecture` already enforces for everything under `src/scoutmb/`)
- [ ] `GET /runs/<run_id>/<file>` still serves generated run artifacts from `settings.runs_dir`

**Verify:** `uv run pytest tests/parity/test_local_web_parity.py tests/architecture -q` → PASS

**Recovery:** Keep `ui/server.py`'s own static mount as the one actually serving the frontend;
leave the package mount unreferenced.

**Steps:**

- [ ] **Step 1: Move the static assets and add the package resource marker**

```bash
git mv ui/static src/scoutmb/resources/web_static
```

`src/scoutmb/resources/__init__.py` already exists (from 2a's report-template extraction) and
already makes `resources` a real package `importlib.resources.files("scoutmb.resources")` can
read from both an installed wheel and the copied release root — proven in 2a
(`tests/packaging/test_mechanisms.py::test_resources_readable_from_copied_release_root`). No new
proof is needed for `web_static/`; it is a subdirectory of the same already-verified package.

- [ ] **Step 2: Mount it in `create_app`**

```python
# src/scoutmb/interfaces/web/app.py -- add inside create_app, after registering the router
    from importlib.resources import as_file, files
    from fastapi.staticfiles import StaticFiles

    static_root = files("scoutmb.resources").joinpath("web_static")
    with as_file(static_root) as static_path:
        app.mount("/runs", StaticFiles(directory=settings.runs_dir), name="runs")
        app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
```

> `as_file`'s context manager materializes a real filesystem path even if the package were ever
> read from a zip (untested and unused per the Phase B spec's own scope note on zipped
> distributions) — for the copied-release-root and installed-wheel cases this sub-plan actually
> targets, `static_root` is already a real directory and `as_file` is a cheap no-op wrapper
> around it, not a temp-extraction cost. Using it anyway keeps the mount correct if that
> assumption is ever revisited, at no cost today.
>
> `as_file`'s `with` block must stay open for the app's lifetime, not just `create_app`'s call —
> **verify this before finalizing**: if `as_file` unwinds and the mounted directory were ever a
> temp extraction, files under it would vanish while the app is still serving requests. For a
> real (non-zip) package, `as_file` yields the underlying path directly with no extraction and no
> cleanup-on-exit hazard, which is what makes exiting the `with` block immediately safe here —
> but this reasoning, not just the code, is what must survive review.

- [ ] **Step 3: Extend the parity test**

```python
# tests/parity/test_local_web_parity.py -- add
@pytest.mark.anyio
async def test_root_serves_the_frontend(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as client:  # _client_for is an @asynccontextmanager
        response = await client.get("/")          # (sub-plan 3, Task B8.3) -- no `await` before it
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
```

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/parity/test_local_web_parity.py tests/architecture -q
```

```bash
git add src/scoutmb/interfaces/web/app.py src/scoutmb/resources/web_static tests/parity/test_local_web_parity.py
git commit -m "feat(web): serve the frontend from scoutmb.resources, fixing sub-plan 3's static-mount gap"
```

---

## Task B10.1: Arm `pdf_to_scouts.py` in `SHIMMED_MODULES`

**Goal:** Fix the shape check's canonical main-guard blind spot (documented as a known gap since
2a) and add `pdf_to_scouts.py` — already pure delegation — to `SHIMMED_MODULES`.

**Files:**
- Modify: `tests/architecture/test_dependency_rules.py` (shape-check special-case for the
  canonical main-guard; `SHIMMED_MODULES` gains `"pdf_to_scouts.py"`)

**Acceptance Criteria:**
- [ ] `if __name__ == "__main__": raise SystemExit(main())` at module top level no longer trips
      the shape check
- [ ] Any *other* top-level `if` still trips it (the special case is narrow, not a blanket
      allowance for `ast.If`)
- [ ] `pdf_to_scouts.py` passes `test_shimmed_module_contains_no_business_logic`

**Verify:** `uv run pytest tests/architecture -q` → PASS

**Recovery:** Revert the shape-check change; leave `SHIMMED_MODULES` empty.

**Steps:**

- [ ] **Step 1: Write the narrowing test**

```python
# tests/architecture/test_dependency_rules.py -- add near the shimmed-module tests
def test_shape_check_special_cases_only_the_canonical_main_guard(tmp_path: Path) -> None:
    """The canonical `if __name__ == "__main__": raise SystemExit(main())` guard must NOT trip
    the shape check. A structurally different top-level `if` (e.g. a real conditional branch)
    still must -- this proves the special case is narrow, not a blanket ast.If allowance."""
    canonical = tmp_path / "canonical_shim.py"
    canonical.write_text(
        "from scoutmb.core.models import ScoutInput  # noqa: F401\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(0)\n"
    )
    assert _shape_check_offenders(canonical) == []

    real_conditional = tmp_path / "not_a_shim.py"
    real_conditional.write_text(
        "import sys\n"
        "if sys.platform == 'win32':\n"
        "    import winreg  # noqa: F401\n"
    )
    assert _shape_check_offenders(real_conditional) != []
```

Run: `uv run pytest tests/architecture/test_dependency_rules.py -k main_guard -v` → FAIL
(`_shape_check_offenders` doesn't exist as a standalone callable yet — the logic is currently
inlined in the parametrized test body)

- [ ] **Step 2: Extract the shape-check body into a callable, add the main-guard special case**

```python
# tests/architecture/test_dependency_rules.py -- replace the body of
# test_shimmed_module_contains_no_business_logic with a call to this extracted function
def _is_canonical_main_guard(node: ast.If) -> bool:
    """`if __name__ == "__main__": raise SystemExit(main())` -- exactly this shape, nothing
    looser. Matched structurally (comparison target/operator/value, and the body being exactly
    one `raise SystemExit(<call>)` statement) rather than by source-text comparison, so
    formatting differences (quotes, spacing) don't matter but a semantically different guard
    still fails to match."""
    test = node.test
    if not (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    ):
        return False
    if node.orelse:
        return False
    if len(node.body) != 1:
        return False
    (stmt,) = node.body
    return (
        isinstance(stmt, ast.Raise)
        and isinstance(stmt.exc, ast.Call)
        and isinstance(stmt.exc.func, ast.Name)
        and stmt.exc.func.id == "SystemExit"
    )


def _shape_check_offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.If) and _is_canonical_main_guard(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for inner in ast.walk(node):
                if isinstance(inner, (ast.If, ast.For, ast.While, ast.Try, ast.BinOp)):
                    offenders.append(f"{path}:{inner.lineno} {type(inner).__name__}")
            continue
        offenders.append(f"{path}:{node.lineno} {type(node).__name__}")
    return offenders


SHIMMED_MODULES: tuple[str, ...] = ("pdf_to_scouts.py",)


@pytest.mark.parametrize("relative", SHIMMED_MODULES)
def test_shimmed_module_contains_no_business_logic(relative: str) -> None:
    path = Path(__file__).resolve().parents[2] / relative
    assert _shape_check_offenders(path) == []
```

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/architecture -q
```

```bash
git add tests/architecture/test_dependency_rules.py
git commit -m "fix(architecture): special-case the canonical main-guard in the shim shape check; arm pdf_to_scouts.py"
```

---

## Task B10.2: Final cutover — a real package pipeline; `scout_schedule_cli.py`/`interfaces/cli/schedule.py` both become thin shims over it

**Goal:** The full CLI batch orchestration (load inputs, launch one browser, drive every scout
through a **shared** breaker/checkpoint/`RunIdentity`, publish the report, all bracketed by
`RunStateMachine`) moves into `features/acquisition/pipeline.py` — a package module that
survives Task B10.4's deletion of `scout_schedule_cli.py`. Both `scout_schedule_cli.async_main`
(a Form-2 shim, needed only because the frozen characterization suite still calls it by name)
and `interfaces/cli/schedule.py`'s `main()` (built in sub-plan 3, which previously delegated
straight to `scout_schedule_cli.async_main` — that dependency is removed here) call this one
function directly.

**Revision note (post-Codex review):** An earlier draft of this task had the breaker
reconstructed fresh inside `process_scout` on every call — meaning it could never see more than
one scout's failures at a time, making `ACQ-BREAKER-*`'s entire cross-scout premise
unsatisfiable. It also never touched the checkpoint store at all (contradicting sub-plan 1's own
`ACQ-RESUME-*` reclassification), recorded every exception — including a real
`KeyboardInterrupt`/cancellation — as `RunEvent.FAIL`, and applied `RunEvent.COMPLETE` before the
report had actually been generated, so a reporting failure after a clean acquisition would leave
the state machine claiming a successful run that never finished. All fixed below. This also
resolves a separate, independently-found defect: `interfaces/cli/schedule.py` (sub-plan 3)
imported `scout_schedule_cli.async_main` directly, which Task B10.4 then deletes with nothing
ever repointed — the new package pipeline is what that entrypoint calls instead.

**Files:**
- Create: `src/scoutmb/features/acquisition/pipeline.py`
- Modify: `src/scoutmb/features/acquisition/batch.py` (`run_batch` gains optional
  `progress_callback`/`resume_event` parameters — the pause/resume and per-scout progress
  reporting the legacy loop has, which sub-plan 1's `run_batch` did not need to support until
  this, its one real caller, exists)
- Modify: `scout_schedule_cli.py` (`process_scout`, `async_main` become Form-2 shims)
- Modify: `src/scoutmb/interfaces/cli/schedule.py` (sub-plan 3's `main()` — calls the new
  pipeline directly instead of `scout_schedule_cli.async_main`)
- Modify: `tests/architecture/test_dependency_rules.py` (`SHIMMED_MODULES` gains
  `"scout_schedule_cli.py"`)
- Test: `tests/integration/test_acquisition_pipeline.py`

**Acceptance Criteria:**
- [ ] A single `RetryPolicy` is constructed **once per pipeline run** (not once per scout) and
      threaded through every scout via `run_batch` — the breaker's cross-scout premise is
      satisfiable, proven by a test with 3+ scouts where a threshold-2 breaker opens on the
      second failure and the third scout is never attempted
- [ ] The checkpoint store is actually used: a resumed run (same `--output` directory) skips
      scouts already in a prior run's checkpoint and reuses their `output_id`s
- [ ] `RunEvent.COMPLETE` is applied only after the report has been generated — a reporting
      failure after a clean acquisition applies `RunEvent.FAIL`, not a state machine that claims
      success
- [ ] A real `asyncio.CancelledError` (what a `KeyboardInterrupt` becomes inside the running
      coroutine once `asyncio.run` cancels it) is mapped to `RunEvent.CANCEL` then
      `RunEvent.CANCELLED` — never `RunEvent.FAIL`
- [ ] `process_scout` is a one-call forwarding shim; `async_main` is a thin wrapper around
      `run_schedule_pipeline`
- [ ] `interfaces/cli/schedule.py`'s `main()` calls `run_schedule_pipeline` directly — it does
      **not** import `scout_schedule_cli`
- [ ] Every `ACQ-*`/`CLI-SCHED-*` execution key still passes both the legacy and package runners
- [ ] `scout_schedule_cli.py` passes `test_shimmed_module_contains_no_business_logic`

**Verify:** `uv run pytest tests/characterization/test_acquisition_matrix.py tests/parity/test_acquisition_parity.py tests/characterization/test_cli_sched_matrix.py tests/integration/test_acquisition_pipeline.py tests/architecture -q` → PASS

**Recovery:** Revert `process_scout`/`async_main`/`interfaces/cli/schedule.py` to their
pre-cutover bodies (sub-plan 1/3 states); keep `run_schedule_pipeline` merged but not the
composed default.

**Steps:**

- [ ] **Step 1: Extend `run_batch` to support pause/resume and progress reporting**

```python
# src/scoutmb/features/acquisition/batch.py -- extend run_batch's signature and loop body
async def run_batch(
    scouts: Sequence[ScoutInput],
    *,
    service: AcquisitionService,
    retry_policy: RetryPolicy,
    checkpoint_store: CheckpointStore,
    run_identity: RunIdentity,
    config: AcquisitionConfig,
    raw_dir: Path,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: "asyncio.Event | None" = None,
    run_state: "RunStateMachine | None" = None,
) -> list[ScoutResult]:
    checkpoint = checkpoint_store.load()
    if checkpoint is not None:
        run_identity.hydrate(checkpoint.output_ids)
    completed_urls = set(checkpoint.completed_urls) if checkpoint is not None else set()

    total = len(scouts)
    results: list[ScoutResult] = []
    was_paused = False
    for index, scout in enumerate(scouts, start=1):
        if scout.url in completed_urls:
            continue

        if resume_event is not None and not resume_event.is_set():
            if run_state is not None and not was_paused:
                from scoutmb.core.run_state import RunEvent

                run_state.apply(RunEvent.PAUSE)
                was_paused = True
            if progress_callback is not None:
                await progress_callback({"type": "paused", "index": index, "total": total})
            await resume_event.wait()
            if run_state is not None and was_paused:
                from scoutmb.core.run_state import RunEvent

                run_state.apply(RunEvent.RESUME)
                was_paused = False
            if progress_callback is not None:
                await progress_callback({"type": "resumed", "index": index, "total": total})

        if progress_callback is not None:
            await progress_callback(
                {"type": "scout_start", "index": index, "total": total, "name": scout.name or scout.url}
            )

        retry_policy.check_closed()  # raises BreakerOpen before opening a session for this scout
        result = await service.process(
            scout=scout, config=config, raw_dir=raw_dir, run_identity=run_identity
        )
        results.append(result)

        if progress_callback is not None:
            await progress_callback(
                {
                    "type": "scout_done", "index": index, "total": total,
                    "name": scout.name or scout.url, "attendee_id": result.attendee_id,
                    "classes": len(result.classes), "requirements": len(result.requirements),
                    "errors": len(result.errors),
                }
            )

        if result.errors:
            retry_policy.record_failure()
        else:
            retry_policy.record_success()

        completed_urls.add(scout.url)
        checkpoint_store.save(
            Checkpoint(
                version=CHECKPOINT_VERSION,
                completed_urls=tuple(completed_urls),
                output_ids=run_identity.snapshot(),
            )
        )

    return results
```

```python
# src/scoutmb/features/acquisition/batch.py -- add to the existing imports
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scoutmb.core.run_state import RunStateMachine
```

> `tests/integration/test_acquisition_batch.py` (sub-plan 1, Task B5.5) calls `run_batch` with
> only its originally-required keyword arguments — the three new parameters all default to
> `None` and are backward compatible, so that test file needs no change.

- [ ] **Step 2: Write the failing pipeline test**

```python
# tests/integration/test_acquisition_pipeline.py
"""B10.2: the breaker is genuinely shared across a whole pipeline run (not rebuilt per scout,
a real bug an earlier draft had), RunEvent.COMPLETE only follows a successful report, and a real
CancelledError maps to CANCEL/CANCELLED rather than FAIL."""

from __future__ import annotations

import asyncio

import pytest

from scoutmb.config import ScheduleConfig
from scoutmb.core.run_state import RunState
from scoutmb.features.acquisition.pipeline import run_schedule_pipeline


async def test_breaker_is_shared_across_the_whole_pipeline_run(tmp_path, monkeypatch) -> None:
    """Three scouts, a fake Playwright stack whose EVERY schedule fetch fails, and a
    threshold-2 breaker (monkeypatched into the pipeline's construction) -- the third scout must
    never be attempted because the breaker opened on the second scout's failure. This is only
    possible if the SAME RetryPolicy instance sees both failures."""
    # This test needs the pipeline's internal browser-launch swapped for the strict fakes, the
    # same way tests/vertical/test_legacy_flows.py already does for the flat script -- read that
    # file's async_playwright monkeypatch pattern (a fake context manager whose chromium.launch
    # returns a StrictFakeBrowser) and mirror it here for run_schedule_pipeline instead of
    # scout_schedule_cli.main. Write a scouts.csv fixture with 3 rows via tests.factories.inputs,
    # monkeypatch scoutmb.features.acquisition.pipeline.async_playwright to that fake, and set
    # breaker_threshold low enough (patch the pipeline's RetryPolicy construction or add a
    # threshold parameter to run_schedule_pipeline if one doesn't already exist) that the third
    # scout is observably never reached -- assert on the number of StrictFakeBrowser contexts
    # opened, exactly like tests/integration/test_acquisition_batch.py already does one layer
    # down for run_batch() directly.
    pytest.skip("finish wiring the strict-fake browser substitution before removing this skip")


async def test_complete_is_not_applied_until_reporting_succeeds(tmp_path, monkeypatch) -> None:
    from scoutmb.features.acquisition import pipeline as pipeline_module

    async def _boom_reporting_service():
        class _ExplodingSink:
            def publish(self, *args: object, **kwargs: object) -> None:
                raise RuntimeError("simulated reporting failure")

        return _ExplodingSink()

    # Same note as above: substitute a fake browser/gateway that succeeds instantly for zero
    # scouts (an empty scouts.csv is the simplest way to reach the reporting call without any
    # real acquisition), then monkeypatch build_reporting_service to return something that
    # raises, and assert the RAISED exception propagates AND that inspecting the pipeline's
    # RunStateMachine (return it or expose it for the test, whichever this task's real
    # implementation makes possible) shows RunState.FAILED, never RunState.COMPLETED.
    pytest.skip("finish wiring the exploding-reporting-service substitution before removing this skip")


async def test_cancellation_maps_to_cancel_not_fail() -> None:
    """A direct, dependency-free proof of the mapping itself: run_schedule_pipeline's own
    except-clause ordering, exercised by injecting a CancelledError at the earliest possible
    point (before any real I/O) via a monkeypatched load step."""
    pytest.skip(
        "inject asyncio.CancelledError at the pipeline's input-loading step (the first "
        "awaited call) and assert the pipeline's RunStateMachine ends in RunState.CANCELLED, "
        "matching the same monkeypatch-and-inspect pattern as the two tests above"
    )
```

> **This test file is intentionally left with three skipped placeholders, not fabricated
> passing tests.** Writing a genuinely realistic fake-browser substitution for
> `run_schedule_pipeline` (as opposed to `run_batch`, which sub-plan 1's own
> `test_acquisition_batch.py` already fakes cleanly since it takes the gateway directly) requires
> reading `tests/vertical/test_legacy_flows.py`'s existing `async_playwright` monkeypatch pattern
> in full first — this plan has not done that reading, and inventing the substitution blind here
> would risk exactly the kind of unverified-claim defect this whole revision pass exists to
> catch. Do this reading and replace the three skips with real assertions before this task is
> considered done; do not let the skips silently ship as this task's actual test coverage.

- [ ] **Step 3: Implement the pipeline**

```python
# src/scoutmb/features/acquisition/pipeline.py
"""The full CLI batch pipeline (D22, D33): load inputs, launch one browser for the run, drive
every scout through run_batch's shared breaker/checkpoint/RunIdentity, publish the report, all
bracketed by one RunStateMachine. The single home for this orchestration -- both
scout_schedule_cli.async_main (a Form-2 shim) and interfaces/cli/schedule.py's main() call this
directly, so neither depends on the other existing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.files.tabular import TabularAttendeeSource
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.config import ScheduleConfig
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutResult
from scoutmb.core.run_state import RunEvent, RunStateMachine
from scoutmb.features.acquisition.batch import run_batch
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.features.ingest.service import IngestService
from scoutmb.interfaces.cli.composition import build_reporting_service
from scoutmb.ports.clock import MonotonicSleeper, SeededJitter

BREAKER_THRESHOLD = 5
"""A NEW, previously-uncharacterized default this task introduces -- the legacy loop had no
breaker at all, so there is no prior value to preserve. This needs a decision before landing,
not an invented number: pick a threshold with whoever owns operational behavior for this tool,
or add a --breaker-threshold flag to ScheduleConfig/parse_args defaulting to whatever is chosen,
so it is reviewable and changeable without another code edit."""


async def run_schedule_pipeline(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    run_state = RunStateMachine()
    run_state.apply(RunEvent.START)

    try:
        scouts = IngestService(
            sources=(TabularAttendeeSource(sheet_name=config.sheet),),
            include_adults=config.include_adults,
        ).load(config.input)
        config.output.mkdir(parents=True, exist_ok=True)
        raw_dir = config.output / "raw"

        print(f"Loaded {len(scouts)} attendee QR link(s).")
        if progress_callback is not None:
            await progress_callback({"type": "batch_start", "total": len(scouts)})

        run_identity = RunIdentity()
        retry_policy = RetryPolicy(
            sleeper=MonotonicSleeper(), jitter=SeededJitter(), breaker_threshold=BREAKER_THRESHOLD
        )
        checkpoint_store = AtomicFileCheckpointStore(config.output / "checkpoint.json")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=not config.headed, channel=config.channel
            )
            try:
                gateway = PlaywrightScoutingEventGateway(
                    browser, allow_dead_assets=config.allow_dead_assets
                )
                service = AcquisitionService(
                    gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink()
                )
                results: list[ScoutResult] = await run_batch(
                    scouts,
                    service=service,
                    retry_policy=retry_policy,
                    checkpoint_store=checkpoint_store,
                    run_identity=run_identity,
                    config=AcquisitionConfig(
                        timeout_seconds=config.timeout, request_delay_ms=config.request_delay_ms
                    ),
                    raw_dir=raw_dir,
                    progress_callback=progress_callback,
                    resume_event=resume_event,
                    run_state=run_state,
                )
            finally:
                await browser.close()

        build_reporting_service().publish(
            config.output,
            results,
            generated_at_local=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            generated_at_iso=datetime.now().astimezone().isoformat(timespec="seconds"),
            run_identity=run_identity,
            generate_html=not config.no_html,
            html_name=config.html_name,
            generate_email_report=config.email_report,
        )
        # Only recorded AFTER the report has actually been generated -- an earlier draft applied
        # COMPLETE right after the acquisition loop, so a reporting failure following a clean
        # acquisition would leave the state machine claiming a run that never actually finished.
        run_state.apply(RunEvent.COMPLETE)
    except asyncio.CancelledError:
        # What a real KeyboardInterrupt becomes inside this coroutine once asyncio.run cancels
        # it -- distinguished from an ordinary failure, never mapped to FAIL.
        run_state.apply(RunEvent.CANCEL)
        run_state.apply(RunEvent.CANCELLED)
        raise
    except Exception:
        run_state.apply(RunEvent.FAIL)
        raise

    print(f"Results written to: {config.output.resolve()}")
    return 1 if any(result.errors for result in results) else 0
```

- [ ] **Step 4: `process_scout`/`async_main` become thin shims**

```python
# scout_schedule_cli.py -- replace process_scout's body entirely
async def process_scout(
    browser: Browser,
    scout: ScoutInput,
    config: ScheduleConfig,
    raw_dir: Path,
    run_identity: RunIdentity | None = None,
) -> ScoutResult:
    from scoutmb.adapters.files.atomic import AtomicFileSink
    from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
    from scoutmb.features.acquisition.pipeline import BREAKER_THRESHOLD
    from scoutmb.features.acquisition.retry import RetryPolicy
    from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
    from scoutmb.ports.clock import MonotonicSleeper, SeededJitter

    run_identity = run_identity or RunIdentity()
    gateway = PlaywrightScoutingEventGateway(browser, allow_dead_assets=config.allow_dead_assets)
    retry_policy = RetryPolicy(
        sleeper=MonotonicSleeper(), jitter=SeededJitter(), breaker_threshold=BREAKER_THRESHOLD
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    return await service.process(
        scout=scout,
        config=AcquisitionConfig(
            timeout_seconds=config.timeout, request_delay_ms=config.request_delay_ms
        ),
        raw_dir=raw_dir,
        run_identity=run_identity,
    )
```

`process_scout` sources `BREAKER_THRESHOLD` from `pipeline.py` (a plain top-level import — no
circularity, since `pipeline.py` never imports `scout_schedule_cli`), so the shim's breaker
threshold and the pipeline's stay the same constant rather than two independently-maintained
numbers.

```python
# scout_schedule_cli.py -- async_main becomes a thin wrapper
async def async_main(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    from scoutmb.features.acquisition.pipeline import run_schedule_pipeline

    return await run_schedule_pipeline(
        config, progress_callback=progress_callback, resume_event=resume_event
    )
```

- [ ] **Step 5: Re-point `interfaces/cli/schedule.py` at the pipeline, not `scout_schedule_cli`**

```python
# src/scoutmb/interfaces/cli/schedule.py -- full replacement; this module no longer imports
# scout_schedule_cli at all, so Task B10.4's deletion of that file cannot break it. The argparse
# construction is a duplicate of scout_schedule_cli.parse_args's (both read their defaults from
# ScheduleConfig, sub-plan 2's Task B6, so the two cannot silently drift on default VALUES --
# only the flag/help text structure is duplicated here, matching this codebase's existing
# precedent for a flat-script/package shim boundary, e.g. features/reporting/service.py's own
# module docstring: "duplicate scout_schedule_cli.py's same-named functions rather than
# importing them... kept in lockstep by inspection.")
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from scoutmb.config import ScheduleConfig

_DEFAULTS = ScheduleConfig(input=Path("unused"))


def parse_args(argv: list[str] | None = None) -> ScheduleConfig:
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
        "combined CSV) in an 'emails' subdirectory of the output directory."
    ))
    args = parser.parse_args(argv)
    return ScheduleConfig(
        input=args.input, sheet=args.sheet, output=args.output, headed=args.headed,
        channel=args.channel, timeout=args.timeout, request_delay_ms=args.request_delay_ms,
        scout_delay_ms=args.scout_delay_ms, allow_dead_assets=args.allow_dead_assets,
        include_adults=args.include_adults, no_html=args.no_html, html_name=args.html_name,
        email_report=args.email_report,
    )


def main() -> int:
    from scoutmb.features.acquisition.pipeline import run_schedule_pipeline

    config = parse_args()
    try:
        return asyncio.run(run_schedule_pipeline(config))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Arm the module and run**

```python
# tests/architecture/test_dependency_rules.py
SHIMMED_MODULES: tuple[str, ...] = ("pdf_to_scouts.py", "scout_schedule_cli.py")
```

```bash
uv run pytest tests/characterization/test_acquisition_matrix.py tests/parity/test_acquisition_parity.py tests/characterization/test_cli_sched_matrix.py tests/integration/test_acquisition_pipeline.py tests/architecture -q
```

- [ ] **Step 7: Commit**

```bash
git add scout_schedule_cli.py src/scoutmb/features/acquisition/pipeline.py src/scoutmb/features/acquisition/batch.py src/scoutmb/interfaces/cli/schedule.py tests/architecture/test_dependency_rules.py tests/integration/test_acquisition_pipeline.py
git commit -m "refactor(cli): run_schedule_pipeline is the one home for CLI batch orchestration; process_scout/async_main/troop349-schedule all delegate to it"
```

---

## Task B10.3: Delete `ui/server.py`, `run_app.py`, and their legacy harness

**Goal:** Remove the two flat modules the package's `create_app`/`troop349`/`troop349-schedule`
now fully replace, together with `tests/harnesses/legacy.py` and
`tests/characterization/test_interface_matrix.py`'s legacy-app-only runner.

**Files:**
- Delete: `ui/server.py`, `ui/__init__.py`, `run_app.py`, `tests/harnesses/legacy.py`
- Modify: `tests/characterization/test_interface_matrix.py` → becomes redundant with
  `tests/parity/test_local_web_parity.py`; delete it once the parity test's coverage is
  confirmed to be a superset (Step 1)
- Modify: `bootstrap/build.spec`, `bootstrap/source_sync.py` (drop the now-deleted files —
  full fix lands in Task B11.1; this task only removes the `ui/server.py`/`run_app.py`/`ui/`
  entries so the release build does not reference deleted paths in the interim)

**Acceptance Criteria:**
- [ ] Every `UI-ROUTE-*`/`UI-IMPORT-*` execution key that `test_interface_matrix.py` covered is
      covered by `tests/parity/test_local_web_parity.py` before the former is deleted — checked
      by diffing the two files' case-id coverage, not assumed
- [ ] `troop349` (built in sub-plan 3) is the only way to launch the local UI after this task
- [ ] `uv run pytest -q` has no `ModuleNotFoundError`/`ImportError` for `ui` or the deleted
      harness anywhere in the remaining suite

**Verify:** `uv run pytest -q` → PASS (no collection errors)

**Recovery:** `git revert` this commit; `troop349` stays available as an additional, not
exclusive, launch path.

**Steps:**

- [ ] **Step 1: Confirm coverage parity before deleting anything**

```bash
grep -o 'case_id="UI-[A-Z]*-[0-9]*"' tests/matrix/cases/interface_cases.py | sort -u > /tmp/all_ui_cases.txt
grep -o '_route_UI_ROUTE_[0-9]*' tests/characterization/test_interface_matrix.py | sort -u
```

Cross-reference every case id the legacy runner drives against
`tests/parity/test_local_web_parity.py`'s own case coverage (extended across sub-plan 3's Task
B8.3 and this sub-plan's Task B10.0). **Do not proceed to deletion if any case id has no
package-side equivalent** — extend `test_local_web_parity.py` first.

- [ ] **Step 2: Delete `run_app.py`, in its own commit**

```bash
git rm run_app.py
git commit -m "chore: retire run_app.py, replaced by troop349"
```

- [ ] **Step 3: Delete `ui/`, in its own commit**

```bash
git rm -r ui/
git commit -m "chore: retire ui/server.py, replaced by scoutmb.interfaces.web.app:create_app"
```

- [ ] **Step 4: Delete the legacy harness and its exclusive runner, in a third commit**

```bash
git rm tests/harnesses/legacy.py
git rm tests/characterization/test_interface_matrix.py
git commit -m "chore: retire the legacy web test harness, superseded by tests/parity/test_local_web_parity.py"
```

- [ ] **Step 5: Patch the two build-config files' now-dangling entries**

```python
# bootstrap/build.spec -- remove the four ui/run_app-related datas entries
datas = [
    (app_src("pdf_to_scouts.py"), "app_src"),
    (app_src("scout_schedule_cli.py"), "app_src"),
    (app_src("requirements.txt"), "app_src"),
    (app_src("bootstrap", "probe_msedge.py"), os.path.join("app_src", "_bootstrap_support")),
]
```

```python
# bootstrap/source_sync.py -- drop the two now-deleted entries
_FILES = [
    "pdf_to_scouts.py",
    "scout_schedule_cli.py",
    "requirements.txt",
]
_DIRS: list[str] = []
```

- [ ] **Step 6: Run and commit**

```bash
uv run pytest -q
```

```bash
git add bootstrap/build.spec bootstrap/source_sync.py
git commit -m "chore(bootstrap): drop build/sync entries for the just-deleted ui/run_app.py"
```

---

## Task B10.4: Delete `scout_schedule_cli.py` and `pdf_to_scouts.py`

**Goal:** Remove the last two flat modules and their exclusive characterization runners, now
that Tasks B10.1/B10.2 proved both pure delegation and every case they held has a package-side
parity runner.

**Files:**
- Delete: `scout_schedule_cli.py`, `pdf_to_scouts.py`
- Delete: `tests/characterization/test_acquisition_matrix.py`,
  `tests/characterization/test_browser_matrix.py`, `tests/characterization/test_cli_sched_matrix.py`,
  `tests/characterization/test_pdf_matrix.py`, `tests/characterization/test_process_scout.py`,
  `tests/characterization/test_phase_a_gap_closure.py` (audit its contents first — Step 1)
- Modify: `tests/factories/records.py` (imports `ClassRecord`/`RequirementRecord` from
  `scout_schedule_cli` today — a one-line import fix, not a deletion), `tests/vertical/test_legacy_flows.py`,
  `tests/performance/test_phase_a_baseline.py` (both drive `scout_schedule_cli.main`/`process_scout`/
  `async_main` directly today — repointed to the package pipeline, not deleted; see Step 2)
- Modify: `bootstrap/build.spec`, `bootstrap/source_sync.py` (drop the remaining flat-file
  entries; Task B11.1 replaces them with the package sync)
- Modify: `pyproject.toml` (remove nothing — the three console scripts already point at package
  modules; only `[tool.ruff] extend-exclude` and mypy's `files` omission lists lose these two
  entries, since there is no longer a flat module to exclude)

**Acceptance Criteria:**
- [ ] Both modules pass `test_shimmed_module_contains_no_business_logic` immediately before
      deletion (already true from B10.1/B10.2 — re-verify, don't re-assume)
- [ ] Every execution key the deleted characterization files drove has a passing package-side
      parity runner (same audit discipline as Task B10.3's Step 1)
- [ ] `tests/factories/records.py`, `tests/vertical/test_legacy_flows.py`, and
      `tests/performance/test_phase_a_baseline.py` — all three found by an independent review to
      import the flat modules directly — are fixed **before** deletion, not discovered broken
      after
- [ ] `troop349-pdf`/`troop349-schedule` are the only remaining ways to run the two pipelines
- [ ] `uv run pytest -q` collects cleanly with zero references to either deleted module

**Verify:** `uv run pytest -q` → PASS (no collection errors)

**Recovery:** `git revert` this commit per module — deleting `scout_schedule_cli.py` and
`pdf_to_scouts.py` are two separate commits, so either can be reverted independently.

**Steps:**

- [ ] **Step 1: Audit `test_phase_a_gap_closure.py` before touching it**

This file's own docstring history (`fix(pdf): shim re-exports fitz/DEFAULT_ADULT_TYPES...`) shows
it exercises symbols reached through **both** flat modules and their package equivalents in the
same file — read it fully before deciding whether it deletes wholesale or needs its
package-only assertions kept in a renamed, narrower file. Do not delete it by pattern-matching
the filename against "test_phase_a_*" without this read.

- [ ] **Step 2: Fix the three files an independent review found still importing the flat modules**

None of these three were in the plan's original file list — found only by checking the live
import graph directly (`rg -n '^\s*(import|from) (scout_schedule_cli|pdf_to_scouts)' tests
--glob '*.py'`), which this step's own commit does again as its final check.

```python
# tests/factories/records.py -- one-line import fix, no other change
from scoutmb.core.models import ClassRecord, RequirementRecord
```

`tests/vertical/test_legacy_flows.py` and `tests/performance/test_phase_a_baseline.py` both
drive `scout_schedule_cli.main`/`process_scout`/`async_main` directly through the strict-fake
`async_playwright` monkeypatch (the same pattern `tests/integration/test_acquisition_pipeline.py`,
Task B10.2, needs to read in full anyway). Re-point each file's entry-point call from
`scout_schedule_cli.async_main`/`.main` to
`scoutmb.features.acquisition.pipeline.run_schedule_pipeline` (or, for the ones asserting
argv/exit-code behavior specifically, `scoutmb.interfaces.cli.schedule.main`) — the assertions
themselves (request counts, growth bounds, the five-stage wiring) do not change, since they
characterize the PIPELINE's behavior, not which module happens to expose it. Do not delete
either file: they hold real, non-redundant coverage (a genuine multi-stage PDF→schedule→report
wire-up, and deterministic request-count/growth-bound assertions) that no other test in this
plan reproduces.

```bash
git add tests/factories/records.py tests/vertical/test_legacy_flows.py tests/performance/test_phase_a_baseline.py
git commit -m "fix(tests): repoint the three tests an independent review found still importing the flat modules"
```

- [ ] **Step 3: Re-verify the shape check, then delete `pdf_to_scouts.py`**

```bash
uv run pytest tests/architecture -k shimmed_module -v
git rm pdf_to_scouts.py tests/characterization/test_pdf_matrix.py tests/characterization/test_browser_matrix.py
git commit -m "chore: retire pdf_to_scouts.py"
```

- [ ] **Step 4: Delete `scout_schedule_cli.py`, in its own commit**

```bash
git rm scout_schedule_cli.py tests/characterization/test_acquisition_matrix.py tests/characterization/test_cli_sched_matrix.py tests/characterization/test_process_scout.py
git commit -m "chore: retire scout_schedule_cli.py"
```

- [ ] **Step 5: Update the remaining build/lint config**

```python
# bootstrap/build.spec -- datas now holds only requirements.txt + probe_msedge.py
datas = [
    (app_src("requirements.txt"), "app_src"),
    (app_src("bootstrap", "probe_msedge.py"), os.path.join("app_src", "_bootstrap_support")),
]
```

```python
# bootstrap/source_sync.py -- _FILES now holds only requirements.txt (Task B11.1 adds scoutmb/)
_FILES = ["requirements.txt"]
```

```toml
# pyproject.toml -- [tool.ruff] extend-exclude and mypy's files omission both drop
# "pdf_to_scouts.py" and "scout_schedule_cli.py" -- both files are gone, so there is nothing
# left to exclude.
```

- [ ] **Step 6: Run and commit**

```bash
uv run pytest -q
```

```bash
git add bootstrap/build.spec bootstrap/source_sync.py pyproject.toml
git commit -m "chore: retire the last flat modules; scoutmb is now the sole implementation"
```

---

## Task B11.1: `bootstrap/` syncs the package, not loose files

**Goal:** `bootstrap/source_sync.py` copies `src/scoutmb` into `<app_dir>/scoutmb`;
`bootstrap/build.spec` bundles `src/scoutmb` as package data — the two of the three
release-root change sites the Phase B spec requires that are not already done
(`bootstrap/python_env.py`'s `.pth` entry already puts `app_dir` on `sys.path` with no change
needed, per the spec's own note — verify this claim rather than re-deriving it, since it is a
plan-verified mechanism from the spec, not this sub-plan's own).

**Files:**
- Modify: `bootstrap/source_sync.py` (`_DIRS` gains `src/scoutmb → scoutmb`), `bootstrap/build.spec`
  (`datas` gains `src/scoutmb`)
- Test: `tests/packaging/test_distribution_contents.py` (extend)

**Acceptance Criteria:**
- [ ] `sync_app_source` copies `src/scoutmb`'s full tree (including `resources/` and `py.typed`)
      to `<app_dir>/scoutmb`, leaving `scouts.csv`/`pdf-uploads/`/`runs/` untouched
- [ ] `bootstrap/build.spec`'s `datas` includes `src/scoutmb`, so a built installer actually has
      something to sync (today it would silently no-op — confirmed by reading the current
      `datas` list, which holds none of `src/scoutmb`)
- [ ] `bootstrap/python_env.py`'s existing `.pth` entry is unchanged, and a test proves `scoutmb`
      importable from the copied root through it (not merely asserted from the spec's prose)

**Verify:** `uv run pytest tests/packaging -q` → PASS

**Recovery:** Revert both file changes; the release root stops syncing `scoutmb` and reverts to
whatever the prior sync state was (by this point in the plan, nothing — Task B10.4 already
emptied `_FILES` down to `requirements.txt`, so reverting this task leaves an intentionally
broken release root until it is fixed forward, which is why this task and B10.4 are sequenced
adjacently rather than left with a working gap between them).

**Steps:**

- [ ] **Step 1: Support a (source, dest) pair in `_DIRS`, and change directory copies to
  `dirs_exist_ok=True` merges rather than a fresh `copytree`**

```python
# bootstrap/source_sync.py -- _DIRS becomes a list of (source_relative, dest_relative) pairs;
# the loop already used copytree(..., dirs_exist_ok=True), so a differing dest is the only
# change needed to the copy logic itself.
_FILES = ["requirements.txt"]
_DIRS: list[tuple[str, str]] = [
    ("src/scoutmb", "scoutmb"),
]


def sync_app_source(paths: AppPaths) -> None:
    source_root = _source_root()

    for relative in _FILES:
        src = source_root / relative
        dest = paths.app_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    for src_relative, dest_relative in _DIRS:
        src = source_root / src_relative
        dest = paths.app_dir / dest_relative
        shutil.copytree(src, dest, dirs_exist_ok=True)

    support_dest = paths.app_dir / "_bootstrap_support" / "probe_msedge.py"
    support_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_probe_msedge_source(), support_dest)
```

> The trailing `probe_msedge.py` copy and anything below it in the real file is **unchanged** —
> only `_FILES`/`_DIRS`'s declarations and the `_DIRS` loop's unpacking are touched. Read the
> rest of `sync_app_source`'s current body before editing, since this plan quotes only the part
> that changes.

- [ ] **Step 2: Bundle the package in the PyInstaller spec**

```python
# bootstrap/build.spec -- datas, add the package tree
datas = [
    (app_src("requirements.txt"), "app_src"),
    (app_src("src", "scoutmb"), os.path.join("app_src", "scoutmb")),
    (app_src("bootstrap", "probe_msedge.py"), os.path.join("app_src", "_bootstrap_support")),
]
```

- [ ] **Step 3: Prove `scoutmb` imports from the copied root through the existing `.pth` entry**

```python
# tests/packaging/test_distribution_contents.py -- add
def test_copied_release_root_scoutmb_is_importable_via_the_dot_pth_entry(tmp_path: Path) -> None:
    """bootstrap/python_env.py's .pth entry already appends app_dir to the embedded
    interpreter's sys.path (unchanged by this task, per the Phase B spec's own note that this
    dependency is load-bearing but pre-existing). This proves scoutmb -- not just its
    resources/, which tests/packaging/test_mechanisms.py already covers -- imports from a
    directory laid out exactly like a synced app_dir, with no repository present."""
    import shutil
    import subprocess
    import sys

    app_dir = tmp_path / "app_dir"
    app_dir.mkdir()
    shutil.copytree("src/scoutmb", app_dir / "scoutmb")

    pth_file = app_dir / "_app_dir.pth"
    pth_file.write_text(str(app_dir) + "\n", encoding="utf-8")

    probe = (
        "import sys; sys.path.insert(0, %r)\n"
        "import scoutmb.core.models\n"
        "print('SCOUTMB_IMPORT_OK')\n"
    ) % str(app_dir)
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "SCOUTMB_IMPORT_OK" in result.stdout
```

> This test simulates the `.pth` mechanism with an explicit `sys.path.insert` inside the probe
> (per the Phase B spec's own warning: `python -I` ignores `PYTHONPATH`, so a real `.pth` file
> read by a bare `-I` interpreter needs to actually sit in a directory Python scans for `.pth`
> files at startup — `site-packages`, not an arbitrary temp dir — to be picked up automatically;
> reproducing that exactly would require constructing a real venv). The `sys.path.insert` line
> inside the executed source is the pattern the spec's own `run_import_probe` reference uses for
> this same reason. **If a reviewer wants the actual `.pth`-file-in-site-packages mechanism
> proven end to end rather than simulated, that is a larger test (a real venv, `.pth` file
> written into its `site-packages`) and should be called out as its own task rather than folded
> in here** — this test proves `scoutmb` imports from a copied root laid out like the real one,
> which is the specific gap this task's Acceptance Criteria name.

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/packaging -q
```

```bash
git add bootstrap/source_sync.py bootstrap/build.spec tests/packaging/test_distribution_contents.py
git commit -m "feat(bootstrap): sync src/scoutmb into the release root instead of loose flat files"
```

---

## Task B11.2: Release-root acceptance sequence

**Goal:** The specific sequence Gate 2 requires: copy the release root to a directory outside
the repository, remove the repository from the environment, launch under conditions matching the
embedded interpreter configuration, and confirm the health endpoint responds and one report
renders.

**Files:**
- Test: `tests/packaging/test_release_root.py`

**Acceptance Criteria:**
- [ ] The copied root (outside the repo, repo path removed from `sys.path`/`PYTHONPATH`) starts
      the package's `create_app` and answers `GET /api/health`
- [ ] The archive excludes private tests, logs, and secrets (`test_archives_exclude_private_tests_logs_and_secrets`,
      already named in the preliminary plan's Named Tests — implement it here since B11 is where
      the archive contents are finalized)
- [ ] `py.typed` and `resources/` are present **inside the built wheel's contents**, not merely
      the source tree (re-verifies 2a's own wheel test still holds once the package sync changed)

**Verify:** `uv run pytest tests/packaging -q` → PASS

**Recovery:** Keep the working (pre-this-task) source-copy manifest; fix the package-data/build
rule that regressed; never add a runtime fallback to repository files as a workaround.

**Steps:**

- [ ] **Step 1: Write the acceptance sequence test**

```python
# tests/packaging/test_release_root.py
"""Gate 2's release-root acceptance sequence: copy the root outside the repo, remove the repo
from the environment, launch, confirm health + one report renders. This is the SEQUENCE the
Phase B spec names as the acceptance condition -- not a claim, a specific reproducible check."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_copied_release_root_starts_and_renders_a_report(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir()
    shutil.copytree(REPO_ROOT / "src" / "scoutmb", release_root / "scoutmb")
    shutil.copy2(REPO_ROOT / "requirements.txt", release_root / "requirements.txt")
    output_dir = tmp_path / "output"

    # Both halves of Gate 2's acceptance sequence in one probe: the health endpoint answers,
    # AND a real report.html renders through the composition root's own ReportingService --
    # not just a health check, which would only prove the app boots, not that reporting works
    # from a copied root with no repository present.
    probe = (
        "import sys; sys.path.insert(0, %r)\n"
        "from scoutmb.interfaces.web.app import create_app\n"
        "from scoutmb.config import UiSettings\n"
        "from scoutmb.interfaces.cli.composition import build_reporting_service\n"
        "from scoutmb.core.identity import RunIdentity\n"
        "from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutResult\n"
        "from fastapi.testclient import TestClient\n"
        "import tempfile, pathlib\n"
        "\n"
        "with tempfile.TemporaryDirectory() as data_dir:\n"
        "    app = create_app(UiSettings(data_root=pathlib.Path(data_dir)))\n"
        "    with TestClient(app) as client:\n"
        "        response = client.get('/api/health')\n"
        "        assert response.status_code == 200, response.text\n"
        "        assert response.json() == {'status': 'ok'}\n"
        "\n"
        "result = ScoutResult(\n"
        "    name='Avery Example', qr_url='https://scoutingevent.com/mobile/x', attendee_id='A1',\n"
        "    classes=(ClassRecord(scout_name='Avery Example', attendee_id='A1', class_number='1',\n"
        "        class_p4_id='C1', class_name='Chess', days='', period_name='', start_time='',\n"
        "        start_time_24h='', location='', has_requirements=True, class_completed=False,\n"
        "        raw_class_name=''),),\n"
        "    requirements=(RequirementRecord(scout_name='Avery Example', attendee_id='A1',\n"
        "        class_number='1', class_p4_id='C1', merit_badge_name='Chess', requirement_id='R1',\n"
        "        requirement_type_id='1', requirement_number='#1', description='Show up.',\n"
        "        completed_requirement=False, completed_class=False, requirement_on_event=True,\n"
        "        present_days=''),),\n"
        "    errors=(),\n"
        ")\n"
        "output_dir = pathlib.Path(%r)\n"
        "build_reporting_service().publish(\n"
        "    output_dir, [result], generated_at_local='2026-08-05 09:00:00 UTC',\n"
        "    generated_at_iso='2026-08-05T09:00:00+00:00', run_identity=RunIdentity(),\n"
        ")\n"
        "report_html = output_dir / 'report.html'\n"
        "assert report_html.is_file() and report_html.stat().st_size > 0, 'report.html did not render'\n"
        "print('RELEASE_ROOT_ACCEPTANCE_OK')\n"
    ) % (str(release_root), str(output_dir))

    # Run from release_root itself, with REPO_ROOT absent from sys.path/PYTHONPATH/cwd --
    # the "remove the repository from the environment" half of the acceptance sequence.
    env = {"PATH": "/usr/bin:/bin"}  # deliberately minimal; no PYTHONPATH, no repo-derived vars
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=release_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "RELEASE_ROOT_ACCEPTANCE_OK" in result.stdout
```

- [ ] **Step 2: Run and commit**

```bash
uv run pytest tests/packaging/test_release_root.py -q
```

```bash
git add tests/packaging/test_release_root.py
git commit -m "test(packaging): prove the release-root acceptance sequence end to end"
```

---

## Sub-plan gate (feeds Gate 2 — the final one)

- All four flat modules deleted, each in its own commit, each proven pure delegation via the
  shape check immediately before its deletion (`ui/server.py` and `run_app.py` split into two
  separate commits, not one).
- `tests/harnesses/legacy.py` removed with them.
- `features/acquisition/pipeline.py` is the one home for CLI batch orchestration: the breaker is
  genuinely shared across every scout in a run, the checkpoint store is actually wired in,
  `RunEvent.COMPLETE` follows a successful report (not just a successful acquisition loop), and a
  real cancellation maps to `CANCEL`/`CANCELLED`, never `FAIL`.
- `troop349`/`troop349-pdf`/`troop349-schedule` are the only remaining entry points, and
  `troop349-schedule` calls the package pipeline directly — it does not import
  `scout_schedule_cli`.
- `tests/factories/records.py`, `tests/vertical/test_legacy_flows.py`, and
  `tests/performance/test_phase_a_baseline.py` — all found by independent review to still import
  a flat module — are fixed, not merely noted.
- `bootstrap/source_sync.py`/`build.spec` sync and bundle `src/scoutmb`, not loose flat files.
- The release-root acceptance sequence passes: copied outside the repo, repo absent from the
  environment, health responds, one report renders.
- `uv run pytest -q` green, zero collection errors, no reference to a deleted module anywhere.
- This completes Gate 2 for the whole of Slice 2b, combined with the other three sub-plans'
  gates (gateway/acquisition, config/run-state, web boundary/compose).

**NO-GO:** `git revert` the specific module's retirement commit; restore the corresponding
compatibility adapter as the composed default; return the defect to its task; rerun this gate.
