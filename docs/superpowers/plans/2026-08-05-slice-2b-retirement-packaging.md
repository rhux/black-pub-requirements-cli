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
>
> **Revision note (post-Codex review, third pass):** The fix above put
> `features/acquisition/pipeline.py` in direct violation of the dependency-edge table — it
> imported four adapters directly and imported UPWARD from `scoutmb.interfaces.cli.composition`,
> both forbidden for a `features/` module. Task B10.2 is rewritten again so
> `run_schedule_pipeline` is pure dependency injection (accepts `scouts`/`service`/
> `retry_policy`/`checkpoint_store`/`reporting_service` already built); all adapter construction
> — including launching the Playwright browser — moves into new builders on
> `interfaces/cli/composition.py` and a new `interfaces/cli/schedule.run()` orchestration
> function that both `main()` and `scout_schedule_cli.async_main`'s shim call. This also
> simplified Task B10.2's own tests: pure DI means the three `run_schedule_pipeline` tests no
> longer need an `async_playwright` monkeypatch at all, so the three `pytest.skip(...)`
> placeholders an earlier draft left there are now real, executable tests. Task B10.4's Step 2
> (the three-file fix) is updated to reflect where a monkeypatch target does and does not exist
> after this change.

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
2a), fix a SEPARATE, independently-found bug where the check walks a function's parameter
ANNOTATIONS along with its body (so any parameter typed `X | None = None` spuriously trips the
`BinOp` check via PEP 604 union syntax, even when the function's actual body is perfectly clean
delegation), and add `pdf_to_scouts.py` — already pure delegation — to `SHIMMED_MODULES`.

**Revision note (post-Codex review):** An independent review found the shape check's
`ast.walk(node)` call at the `FunctionDef`/`AsyncFunctionDef` branch walks the ENTIRE function
node, not just its body -- `node.args` (parameter annotations and defaults) is a child of that
node too, and `SomeType | None` (any modern PEP 604 union-type annotation) parses to `ast.BinOp`
with `ast.BitOr`, structurally indistinguishable from arithmetic to this check. Since
`RunIdentity | None = None`-shaped parameters are used throughout this codebase's own
Slice 2b shims -- Task B10.2's own `process_scout(..., run_identity: RunIdentity | None = None)`
is a direct example -- this bug would have made it IMPOSSIBLE for any of this plan's carefully
-written pure-delegation shims to ever pass the check, regardless of how clean their bodies
actually are. This has been latent since the check was written (Task 24, Slice 2a) because
`SHIMMED_MODULES` has stayed empty until this sub-plan, so nothing ever exercised it. Fixed
below by walking each of the function's own body STATEMENTS, not the function node itself.

**Files:**
- Modify: `tests/architecture/test_dependency_rules.py` (shape-check special-case for the
  canonical main-guard; shape-check now walks only function BODY statements, not parameter
  annotations; `SHIMMED_MODULES` gains `"pdf_to_scouts.py"`)

**Acceptance Criteria:**
- [ ] `if __name__ == "__main__": raise SystemExit(main())` at module top level no longer trips
      the shape check
- [ ] Any *other* top-level `if` still trips it (the special case is narrow, not a blanket
      allowance for `ast.If`)
- [ ] A function whose body is clean delegation but whose signature has a `SomeType | None = None`
      parameter no longer trips the check on that parameter's annotation
- [ ] A function whose BODY (not signature) contains a real `x = a | b` bitwise/union expression
      still trips the check -- the fix narrows scope to exclude annotations, it does not disable
      `BinOp` detection inside the body itself
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


def test_shape_check_ignores_union_type_annotations_but_not_body_binops(tmp_path: Path) -> None:
    """PEP 604 `X | None` parameter annotations parse to ast.BinOp -- structurally identical to
    a real arithmetic/bitwise expression, but not business logic. A clean-bodied shim using this
    (extremely common) modern annotation style must still pass; a function whose BODY actually
    contains a BinOp must still fail -- this proves the fix narrows scope to annotations, it
    does not blanket-disable BinOp detection."""
    clean_shim = tmp_path / "clean_shim.py"
    clean_shim.write_text(
        "from typing import Any\n"
        "def process(name: str, config: Any | None = None) -> str:\n"
        "    return name\n"
    )
    assert _shape_check_offenders(clean_shim) == []

    dirty_body = tmp_path / "dirty_body.py"
    dirty_body.write_text(
        "def compute(a: int, b: int) -> int:\n"
        "    return a | b\n"
    )
    assert _shape_check_offenders(dirty_body) != []
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
            # Walk each BODY STATEMENT individually, never the FunctionDef/ClassDef node
            # itself -- ast.walk(node) would also descend into node.args (parameter
            # annotations/defaults), and a PEP 604 `X | None` annotation parses to ast.BinOp,
            # indistinguishable from a real arithmetic expression to this check. Scoping the
            # walk to node.body excludes annotations entirely while still catching a genuine
            # BinOp INSIDE the body (e.g. `return a | b`).
            for stmt in node.body:
                for inner in ast.walk(stmt):
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
git commit -m "fix(architecture): special-case the canonical main-guard, exclude parameter annotations from the shim shape check; arm pdf_to_scouts.py"
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

**Revision note (post-Codex review, third pass):** An earlier draft of this task had the breaker
reconstructed fresh inside `process_scout` on every call — meaning it could never see more than
one scout's failures at a time, making `ACQ-BREAKER-*`'s entire cross-scout premise
unsatisfiable. It also never touched the checkpoint store at all (contradicting sub-plan 1's own
`ACQ-RESUME-*` reclassification), recorded every exception — including a real
`KeyboardInterrupt`/cancellation — as `RunEvent.FAIL`, and applied `RunEvent.COMPLETE` before the
report had actually been generated, so a reporting failure after a clean acquisition would leave
the state machine claiming a successful run that never finished. All fixed in an earlier revision.
This also resolved a separate, independently-found defect: `interfaces/cli/schedule.py`
(sub-plan 3) imported `scout_schedule_cli.async_main` directly, which Task B10.4 then deletes
with nothing ever repointed — the new package pipeline is what that entrypoint calls instead.

**A SECOND, independently-found defect (this revision):** the draft that fixed the above put
`features/acquisition/pipeline.py` in direct violation of the dependency-edge table — it imported
FOUR adapters directly (`AtomicFileSink`, `AtomicFileCheckpointStore`, `TabularAttendeeSource`,
`PlaywrightScoutingEventGateway`) from a `features/` module, which may only import
`features, core, ports, config, errors` — never `adapters`. It also imported UPWARD from
`scoutmb.interfaces.cli.composition`, which no layer is ever permitted to do (composition roots
import outward into adapters; nothing imports INTO `interfaces/` from below it). Fixed below by
making `run_schedule_pipeline` pure dependency injection: it accepts an already-loaded `scouts`
sequence and already-constructed `service`/`checkpoint_store`/`reporting_service` collaborators,
and owns none of their construction. All adapter wiring — including launching and closing the
Playwright browser — moves into `interfaces/cli/composition.py` (the one module under
`interfaces/cli` permitted to import adapters) and a new orchestration function,
`interfaces/cli/schedule.run()`, that calls those builders and then `run_schedule_pipeline`. This
also, as a side effect, makes the pipeline's own tests dramatically simpler: they no longer need
to monkeypatch `async_playwright` at all, since a pure-DI function accepts plain fakes directly —
the three placeholder `pytest.skip(...)` tests an earlier draft left in `Step 2` are replaced
with real, executable tests below.

**A THIRD, independently-found defect (this revision):** running the actual shim shape-check
logic against the live `scout_schedule_cli.py` file shows this task's `process_scout`/
`async_main` rewrites alone cannot make it pass — roughly a dozen OTHER top-level functions
(`is_schedule_response`, `discover_name`, `annotate_requirement_statuses`,
`render_email_text`/`render_email_html`, `write_email_reports`, `write_html_report`,
`_assert_blank_identity_results_have_no_records`/`_assert_blank_identity_scouts_have_no_records`,
`_attendee_key_for`) still have real `if`/`for`/`try` bodies, kept ONLY as legacy duplicates for
byte-for-byte comparison by specific Category-B characterization tests Task B10.4 deletes. This
task's own Step 7 previously armed `SHIMMED_MODULES` with `"scout_schedule_cli.py"` and claimed
the shape check would pass — it cannot, at this point in the sequence. Fixed by (a) making
`main` a pure re-export of `interfaces.cli.schedule.main` here (Step 5, below — the one
remaining local function this task's own changes can cleanly resolve), and (b) deferring the
`SHIMMED_MODULES` arming entirely to Task B10.4, once its Category B test deletions remove the
dead functions' last callers and it deletes their bodies. A SEPARATE, more fundamental bug was
found in the same pass: the shape check's `ast.walk(node)` call also descends into a function's
parameter ANNOTATIONS, so any `X | None = None` parameter (used throughout this very sub-plan,
e.g. `process_scout`'s own `run_identity: RunIdentity | None = None`) would spuriously trip the
`BinOp` check regardless of how clean the function's actual body is — fixed in Task B10.1, which
already owns this test code. A FOURTH, independently-found defect in the same pass: `run_batch`'s
skip condition (`if scout.url in completed_urls:`, inherited unchanged from sub-plan 1's Task
B5.5 into this task's Step 1 restatement) silently drops a scout from the resumed run's results
when resuming from a checkpoint saved before `completed_results` existed (Task B5.3's
backward-compat load has the URL in `completed_urls` with nothing in `completed_results` to
reconstruct it from) — the exact bug `completed_results` exists to prevent, just triggered by an
old-format file. Fixed below (and in sub-plan 1's own copy) by requiring the URL be present in
BOTH sets before skipping; on the old-format edge case this re-processes the scout once instead
of losing it.

**Files:**
- Create: `src/scoutmb/features/acquisition/pipeline.py`
- Modify: `src/scoutmb/features/acquisition/batch.py` (`run_batch` gains optional
  `progress_callback`/`resume_event`/`run_state` parameters — the pause/resume and per-scout
  progress reporting the legacy loop has, layered on top of sub-plan 1's Task B5.5 checkpoint
  -semantics fixes, which this task's `run_batch` extension must preserve, not revert)
- Modify: `src/scoutmb/interfaces/cli/composition.py` (new builders:
  `build_launched_browser`, `build_schedule_gateway`, `build_checkpoint_store`,
  `build_acquisition_service` — every adapter this CLI path touches, confined here)
- Modify: `scout_schedule_cli.py` (`process_scout`, `async_main` become Form-2 shims; `main`
  becomes a Form-1 re-export of `interfaces.cli.schedule.main` — see the note below on why the
  file's OTHER ~10 legacy-duplicate functions are deliberately NOT touched here)
- Modify: `src/scoutmb/interfaces/cli/schedule.py` (sub-plan 3's `main()` — gains a new `run()`
  orchestration function that composes the adapters via `composition.py` and calls
  `run_schedule_pipeline`; `main()` and `scout_schedule_cli.async_main` both call `run()`)
- Test: `tests/integration/test_acquisition_pipeline.py`

**Note — `scout_schedule_cli.py` does NOT get armed in `SHIMMED_MODULES` by this task.** An
independent review found the file still has roughly a dozen top-level functions with real
control flow after this task's changes land — `is_schedule_response`, `discover_name`,
`_assert_blank_identity_results_have_no_records`, `_assert_blank_identity_scouts_have_no_records`,
`_attendee_key_for`, `annotate_requirement_statuses`, `render_email_text`, `render_email_html`,
`write_email_reports`, `write_html_report` (plus `days_from_class_name`, pending Task B10.4
Step 1's audit of `test_phase_a_gap_closure.py`) — every one of them a **deliberately-kept
legacy duplicate**, each one's own docstring saying it exists ONLY so a specific Category-B
characterization test file (Task B10.4) can compare it against its package equivalent
byte-for-byte. None of them are called from this file's own production path anymore once this
task's `process_scout`/`async_main`/`main` rewrites land — their SOLE remaining callers are the
Category-B test files Task B10.4 deletes. Arming `SHIMMED_MODULES` here, before those callers
(and the dead functions themselves) are gone, would make `test_shimmed_module_contains_no_
business_logic` fail immediately. The arming moves to Task B10.4, after its Category B deletions
land and it deletes these now-orphaned function bodies — see that task's new Step 6.

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
- [ ] `features/acquisition/pipeline.py` imports NO adapter module and does not import anything
      from `scoutmb.interfaces` — `run_schedule_pipeline` receives `scouts`, `service`,
      `retry_policy`, `checkpoint_store`, and `reporting_service` as already-built parameters;
      `tests/architecture`'s existing dependency-edge test covers this module like every other
      `features/` module, with no special-case exemption
- [ ] `interfaces/cli/composition.py` is the ONLY module that constructs the launched Playwright
      browser, the `ScoutingEventGateway`, the `CheckpointStore`, or the `AcquisitionService` for
      the schedule CLI path — `interfaces/cli/schedule.run()` calls those builders and passes
      the results into `run_schedule_pipeline`; it does not construct any adapter itself
- [ ] `process_scout` is a one-call forwarding shim; `async_main` is a thin wrapper delegating to
      `interfaces.cli.schedule.run()`
- [ ] `interfaces/cli/schedule.py`'s `main()` calls its own `run()`, which calls
      `run_schedule_pipeline` — it does **not** import `scout_schedule_cli`
- [ ] Every `ACQ-*`/`CLI-SCHED-*` execution key still passes both the legacy and package runners
- [ ] `scout_schedule_cli.main` is `from scoutmb.interfaces.cli.schedule import main` — a pure
      re-export, matching the existing precedent already established for `pdf_to_scouts.py`'s own
      `main` (Task B10.1) — not a locally-defined function with its own try/except body
- [ ] `scout_schedule_cli.py` is deliberately **not** added to `SHIMMED_MODULES` by this task —
      that happens in Task B10.4, once its remaining legacy-duplicate functions and their
      exclusive test callers are gone (see the Files note above)

**Verify:** `uv run pytest tests/characterization/test_acquisition_matrix.py tests/parity/test_acquisition_parity.py tests/characterization/test_cli_sched_matrix.py tests/integration/test_acquisition_pipeline.py tests/architecture -q` → PASS

**Recovery:** Revert `process_scout`/`async_main`/`interfaces/cli/schedule.py` to their
pre-cutover bodies (sub-plan 1/3 states); keep `run_schedule_pipeline` merged but not the
composed default.

**Steps:**

- [ ] **Step 1: Extend `run_batch` to support pause/resume and progress reporting**

This layers pause/resume/progress-callback support ON TOP of sub-plan 1's Task B5.5 `run_batch`
— which already fixed checkpoint semantics (only mark a scout completed on success, save a
fresh checkpoint at the very start of a run, reconstruct previously-completed scouts into the
returned list via `scout_result_from_row`) and restored the dropped `scout_delay_ms` inter-scout
pacing and per-scout console output. Nothing below reverts any of that — this is the complete,
current function, not a diff against the ORIGINAL pre-sub-plan-1 draft.

```python
# src/scoutmb/features/acquisition/batch.py -- full replacement of run_batch
async def run_batch(
    scouts: Sequence[ScoutInput],
    *,
    service: AcquisitionService,
    retry_policy: RetryPolicy,
    checkpoint_store: CheckpointStore,
    run_identity: RunIdentity,
    config: AcquisitionConfig,
    raw_dir: Path,
    scout_delay_ms: int | None = None,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
    run_state: "RunStateMachine | None" = None,
) -> list[ScoutResult]:
    checkpoint = checkpoint_store.load()
    if checkpoint is None:
        # Create the checkpoint file NOW, before any scout is processed -- ACQ-RESUME-001's
        # "a fresh run creates a checkpoint file at the start of a run" behavior.
        checkpoint = Checkpoint(version=CHECKPOINT_VERSION, completed_urls=(), output_ids={})
        checkpoint_store.save(checkpoint)
    else:
        run_identity.hydrate(checkpoint.output_ids)

    completed_urls = set(checkpoint.completed_urls)
    completed_results = dict(checkpoint.completed_results)
    # Scouts finished on a prior process are reconstructed, not re-fetched -- a resumed run's
    # report must include them alongside whatever this run newly processes.
    results: list[ScoutResult] = [
        scout_result_from_row(row) for row in completed_results.values()
    ]

    total = len(scouts)
    was_paused = False
    for index, scout in enumerate(scouts, start=1):
        # Requires BOTH sets -- see sub-plan 1's Task B5.5 for the full rationale. A
        # same-version checkpoint always adds a URL to both together, so this changes nothing
        # for the normal case; it only prevents silently dropping a scout whose completed_urls
        # entry predates the completed_results field (Task B5.3's backward-compat load).
        if scout.url in completed_urls and scout.url in completed_results:
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

        label = scout.name or scout.url
        print(f"[{index}/{total}] {label}")
        if progress_callback is not None:
            await progress_callback(
                {"type": "scout_start", "index": index, "total": total, "name": label}
            )

        retry_policy.check_closed()  # raises BreakerOpen before opening a session for this scout
        result = await service.process(
            scout=scout, config=config, raw_dir=raw_dir, run_identity=run_identity
        )
        results.append(result)
        print(
            f"    attendeeID={result.attendee_id or 'unknown'}, "
            f"classes={len(result.classes)}, requirements={len(result.requirements)}, "
            f"errors={len(result.errors)}"
        )

        if progress_callback is not None:
            await progress_callback(
                {
                    "type": "scout_done", "index": index, "total": total,
                    "name": label, "attendee_id": result.attendee_id,
                    "classes": len(result.classes), "requirements": len(result.requirements),
                    "errors": len(result.errors),
                }
            )

        if result.errors:
            retry_policy.record_failure()
        else:
            retry_policy.record_success()
            completed_urls.add(scout.url)
            completed_results[scout.url] = scout_result_to_row(result)

        checkpoint_store.save(
            Checkpoint(
                version=CHECKPOINT_VERSION,
                completed_urls=tuple(completed_urls),
                output_ids=run_identity.snapshot(),
                completed_results=completed_results,
            )
        )

        # Only sleep if a not-yet-completed scout remains after this one.
        if any(remaining.url not in completed_urls for remaining in scouts[index:]):
            delay_seconds = (
                random.uniform(0.5, 2.0) if scout_delay_ms is None else scout_delay_ms / 1000
            )
            if delay_seconds > 0:
                await retry_policy.sleeper.sleep(delay_seconds)

    return results
```

```python
# src/scoutmb/features/acquisition/batch.py -- add to the existing imports (random and
# scout_result_from_row/scout_result_to_row are already there from sub-plan 1's Task B5.5)
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scoutmb.core.run_state import RunStateMachine
```

> `tests/integration/test_acquisition_batch.py` (sub-plan 1, Task B5.5) calls `run_batch` with
> only its originally-required keyword arguments plus, in some tests, `scout_delay_ms` — the
> newer `progress_callback`/`resume_event`/`run_state` parameters all default to `None` and are
> backward compatible, so that test file needs no change for THIS task.

- [ ] **Step 2: Write the failing pipeline tests**

Because `run_schedule_pipeline` is pure dependency injection (this revision's whole point), none
of these need `async_playwright` monkeypatching at all — a real `StrictFakeBrowser` wired
straight into a real `PlaywrightScoutingEventGateway`/`AcquisitionService` is a plain constructor
call here, exactly like `tests/integration/test_acquisition_batch.py` already does one layer
down for `run_batch()`. An earlier draft of this task left three `pytest.skip(...)` placeholders
here because faking `async_playwright` looked hard; the actual fix (moving browser construction
out of this module entirely) made that difficulty disappear rather than requiring it be solved.

```python
# tests/integration/test_acquisition_pipeline.py
"""B10.2: the breaker is genuinely shared across a whole pipeline run (not rebuilt per scout,
a real bug an earlier draft had), RunEvent.COMPLETE only follows a successful report, and a real
CancelledError maps to CANCEL/CANCELLED rather than FAIL. run_schedule_pipeline is pure DI --
every collaborator here is a plain fake or a real object built straight from a fake browser, no
async_playwright monkeypatching required."""

from __future__ import annotations

import asyncio

import pytest

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.config import ScheduleConfig
from scoutmb.core.models import ScoutInput
from scoutmb.core.run_state import RunState, RunStateMachine
from scoutmb.features.acquisition.pipeline import run_schedule_pipeline
from scoutmb.features.acquisition.retry import BreakerOpen, RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionService
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock


class _RecordingSleeper:
    async def sleep(self, seconds: float) -> None:
        pass

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


def _config(tmp_path) -> ScheduleConfig:
    # `input` is required by ScheduleConfig but never read here -- scouts are injected directly.
    return ScheduleConfig(input=tmp_path / "unused.csv", output=tmp_path / "out")


class _NoOpReportingService:
    """A ReportingService stand-in for tests that never reach a successful publish (the breaker
    test below raises before the report step) -- duck-types ReportingService.publish's signature
    loosely via **kwargs since these tests only care THAT it was (or wasn't) called, never its
    output."""

    def publish(self, *args: object, **kwargs: object) -> None:
        pass


async def test_breaker_is_shared_across_the_whole_pipeline_run(tmp_path) -> None:
    """Three scouts, every schedule fetch scripted to fail (nothing scripted -> the gateway's
    first call raises), and a threshold-2 breaker -- the third scout must never be attempted,
    proving the SAME RetryPolicy instance run_schedule_pipeline threads into both the
    AcquisitionService AND run_batch sees both of the first two scouts' failures."""
    scouts = [
        ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
        ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
        ScoutInput(name="Casey", url="https://scoutingevent.com/mobile/checkin?t=C"),
    ]
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # nothing scripted -- every fetch fails
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=2)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")

    with pytest.raises(BreakerOpen):
        await run_schedule_pipeline(
            _config(tmp_path),
            scouts=scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=_NoOpReportingService(),
        )
    # Casey must never have been attempted -- the breaker opened after Bailey's failure, before
    # a third BrowserContext could be opened.
    assert len(browser.contexts) == 2


async def test_complete_is_not_applied_until_reporting_succeeds(tmp_path) -> None:
    """A reporting failure after a clean (zero-scout) acquisition must leave the state machine
    in FAILED, never claim COMPLETED for a run that didn't actually finish publishing."""

    class _ExplodingReportingService:
        def publish(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated reporting failure")

    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # never called -- zero scouts
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")
    run_state = RunStateMachine()

    with pytest.raises(RuntimeError, match="simulated reporting failure"):
        await run_schedule_pipeline(
            _config(tmp_path),
            scouts=[],
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=_ExplodingReportingService(),  # type: ignore[arg-type]
            run_state=run_state,
        )

    assert run_state.state is RunState.FAILED


async def test_cancellation_maps_to_cancel_not_fail(tmp_path) -> None:
    """A real asyncio.CancelledError (what a KeyboardInterrupt becomes inside the running
    coroutine once asyncio.run cancels it) maps to CANCEL then CANCELLED -- never FAIL. Injected
    at the reporting step, the last collaborator run_schedule_pipeline calls -- exactly as
    "realistic" a CancelledError source as any other await point inside the try block, and the
    simplest one to inject without touching run_batch's internals."""

    class _CancellingReportingService:
        def publish(self, *args: object, **kwargs: object) -> None:
            raise asyncio.CancelledError()

    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # never called -- zero scouts
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")
    run_state = RunStateMachine()

    with pytest.raises(asyncio.CancelledError):
        await run_schedule_pipeline(
            _config(tmp_path),
            scouts=[],
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=_CancellingReportingService(),  # type: ignore[arg-type]
            run_state=run_state,
        )

    assert run_state.state is RunState.CANCELLED
```

- [ ] **Step 3: Implement the pipeline — pure dependency injection, no adapter/interfaces imports**

```python
# src/scoutmb/features/acquisition/pipeline.py
"""The full CLI batch pipeline orchestration (D22, D33): drive every scout through run_batch's
shared breaker/checkpoint/RunIdentity, publish the report, all bracketed by one RunStateMachine.
The single home for this ORCHESTRATION LOGIC -- both scout_schedule_cli.async_main (a Form-2
shim) and interfaces/cli/schedule.py's run() call run_schedule_pipeline directly, so neither
depends on the other existing.

Pure dependency injection: every adapter this CLI path touches -- the launched Playwright
browser, the ScoutingEventGateway, the CheckpointStore, the AtomicFileSink each collaborator
wraps, the ReportingService -- is constructed by the CALLER and handed in already-built. An
earlier draft imported four adapters directly from this features/ module (AtomicFileSink,
AtomicFileCheckpointStore, TabularAttendeeSource, PlaywrightScoutingEventGateway) plus imported
UPWARD from scoutmb.interfaces.cli.composition -- both violate the dependency-edge table
(`features -> features, core, ports, config, errors`; never `adapters`, never `interfaces`).
interfaces/cli/composition.py now owns all of that construction; interfaces/cli/schedule.py's
run() calls those builders and passes the results in here."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from scoutmb.config import ScheduleConfig
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput, ScoutResult
from scoutmb.core.run_state import RunEvent, RunStateMachine
from scoutmb.features.acquisition.batch import run_batch
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.features.reporting.service import ReportingService
from scoutmb.ports.checkpoint_store import CheckpointStore

BREAKER_THRESHOLD = 5
"""A NEW, previously-uncharacterized default this task introduces -- the legacy loop had no
breaker at all, so there is no prior value to preserve. This needs a decision before landing,
not an invented number: pick a threshold with whoever owns operational behavior for this tool,
or add a --breaker-threshold flag to ScheduleConfig/parse_args defaulting to whatever is chosen,
so it is reviewable and changeable without another code edit. Consumed by
interfaces/cli/schedule.py's run() (and by scout_schedule_cli.process_scout's shim) when
constructing the shared RetryPolicy -- this module only DEFINES the constant, since it no longer
constructs the RetryPolicy that uses it."""


async def run_schedule_pipeline(
    config: ScheduleConfig,
    *,
    scouts: Sequence[ScoutInput],
    service: AcquisitionService,
    retry_policy: RetryPolicy,
    checkpoint_store: CheckpointStore,
    reporting_service: ReportingService,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
    run_state: RunStateMachine | None = None,
) -> int:
    """`retry_policy` MUST be the same instance embedded in `service` -- the caller (composition
    + interfaces/cli/schedule.run()) constructs ONE RetryPolicy and passes it to both, so the
    breaker's cross-scout failure count and the per-request backoff share one set of state. This
    module has no way to enforce that itself (it would require reaching into `service`'s
    internals); it is the caller's contract to uphold, exactly like `run_batch` already
    documents for its own `service`/`retry_policy` pair."""
    run_state = run_state if run_state is not None else RunStateMachine()
    run_state.apply(RunEvent.START)

    try:
        config.output.mkdir(parents=True, exist_ok=True)
        raw_dir = config.output / "raw"

        print(f"Loaded {len(scouts)} attendee QR link(s).")
        if progress_callback is not None:
            await progress_callback({"type": "batch_start", "total": len(scouts)})

        run_identity = RunIdentity()
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
            scout_delay_ms=config.scout_delay_ms,
            progress_callback=progress_callback,
            resume_event=resume_event,
            run_state=run_state,
        )

        reporting_service.publish(
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

- [ ] **Step 4: Add the schedule-CLI adapter builders to `interfaces/cli/composition.py`**

```python
# src/scoutmb/interfaces/cli/composition.py -- add to the existing imports
from collections.abc import AsyncIterator, Sequence  # Sequence already imported; add AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Protocol  # Protocol already imported; add TYPE_CHECKING

from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.errors import CapabilityUnavailable
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionService
from scoutmb.ports.checkpoint_store import CheckpointStore
from scoutmb.ports.scoutevent import ScoutingEventGateway

if TYPE_CHECKING:
    from playwright.async_api import Browser
```

```python
# src/scoutmb/interfaces/cli/composition.py -- append these four builders. Playwright itself is
# imported function-local inside build_launched_browser, not at this module's top level: the
# "acquisition" extra (pyproject.toml) is optional, and every OTHER builder already in this file
# (build_ingest_service, build_reporting_service, build_pdf_extractor) must keep working without
# it installed -- a module-scope playwright import would break composition.py entirely for a
# PDF-only install. This is the ONLY place in the package that calls async_playwright() itself.
@asynccontextmanager
async def build_launched_browser(
    *, headed: bool, channel: str | None
) -> AsyncIterator["Browser"]:
    """Launches ONE Chromium browser for a schedule-CLI run and guarantees it is closed even on
    an exception -- interfaces/cli/schedule.py's run() holds this open for the whole batch, the
    same lifetime scout_schedule_cli.async_main's inline `async with async_playwright()` block
    used to have."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise CapabilityUnavailable(
            capability="acquisition", distributions=("playwright",), extra="acquisition"
        ) from exc

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed, channel=channel)
        try:
            yield browser
        finally:
            await browser.close()


def build_schedule_gateway(browser: "Browser", *, allow_dead_assets: bool) -> ScoutingEventGateway:
    return PlaywrightScoutingEventGateway(browser, allow_dead_assets=allow_dead_assets)


def build_checkpoint_store(path: Path) -> CheckpointStore:
    return AtomicFileCheckpointStore(path)


def build_acquisition_service(
    gateway: ScoutingEventGateway, retry_policy: RetryPolicy
) -> AcquisitionService:
    return AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
```

> `AtomicFileSink` and `Path` are already imported at the top of `composition.py` (used by
> `build_reporting_service`/`build_pdf_extractor`) — nothing new needed for those two names.

- [ ] **Step 5: `process_scout`/`async_main` become thin shims**

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
numbers. This shim constructs its own gateway/service directly, same as before — it is a flat
top-level script, not a module under `src/scoutmb/`, so the hex dependency-edge table (which
`pipeline.py`'s fix above is about) does not constrain it at all.

```python
# scout_schedule_cli.py -- async_main becomes a thin wrapper over interfaces/cli/schedule.run(),
# NOT run_schedule_pipeline directly -- run_schedule_pipeline now requires already-constructed
# scouts/service/retry_policy/checkpoint_store/reporting_service (Step 3's pure-DI fix), and
# composing those is interfaces/cli/schedule.run()'s job, not this shim's.
async def async_main(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    from scoutmb.interfaces.cli.schedule import run

    return await run(config, progress_callback=progress_callback, resume_event=resume_event)
```

`main()`'s local definition (the `try/except KeyboardInterrupt/Exception` wrapper around
`asyncio.run(async_main(...))`) is DELETED entirely, not merely rewritten — its body would still
trip the shape check (a `try` is a `try` regardless of how thin the function around it is), and
`interfaces/cli/schedule.py`'s own `main()` (Step 6, below) is now functionally identical (same
`asyncio.run(run(config))` + `KeyboardInterrupt`→130 + `Exception`→`"ERROR: {exc}"`→2 shape).
Add a pure re-export to the top-of-file import block instead, matching the exact precedent
`pdf_to_scouts.py` already established for its own `main` (Task B10.1):

```python
# scout_schedule_cli.py -- add to the top-of-file import block, alongside the other
# `noqa: F401` legacy-public-surface re-exports; DELETE the local `def main(): ...` definition
# that used to sit near the bottom of the file entirely
from scoutmb.interfaces.cli.schedule import main  # noqa: F401 - legacy public surface
```

The trailing `if __name__ == "__main__": raise SystemExit(main())` guard is untouched — it now
calls the re-exported `main`, and Task B10.1's canonical-main-guard special case still matches
it structurally (the guard's shape doesn't care where `main` was defined).

- [ ] **Step 6: Re-point `interfaces/cli/schedule.py` at the pipeline, not `scout_schedule_cli`**

```python
# src/scoutmb/interfaces/cli/schedule.py -- full replacement; this module no longer imports
# scout_schedule_cli at all, so Task B10.4's deletion of that file cannot break it. The argparse
# construction is a duplicate of scout_schedule_cli.parse_args's (both read their defaults from
# ScheduleConfig, sub-plan 2's Task B6, so the two cannot silently drift on default VALUES --
# only the flag/help text structure is duplicated here, matching this codebase's existing
# precedent for a flat-script/package shim boundary, e.g. features/reporting/service.py's own
# module docstring: "duplicate scout_schedule_cli.py's same-named functions rather than
# importing them... kept in lockstep by inspection.")
#
# run() is the ONE place that composes the schedule CLI's adapters (via composition.py's
# builders) and calls run_schedule_pipeline -- both this module's own main() and
# scout_schedule_cli.async_main's shim call run(), so the composition logic exists exactly once.
from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

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


async def run(
    config: ScheduleConfig,
    *,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_event: asyncio.Event | None = None,
) -> int:
    """Composes the schedule CLI's adapters and calls run_schedule_pipeline. The ONE place that
    does this composition -- main() below and scout_schedule_cli.async_main's shim both call
    this rather than each building their own gateway/checkpoint-store/browser."""
    from scoutmb.features.acquisition.pipeline import BREAKER_THRESHOLD, run_schedule_pipeline
    from scoutmb.features.acquisition.retry import RetryPolicy
    from scoutmb.interfaces.cli.composition import (
        build_acquisition_service,
        build_checkpoint_store,
        build_ingest_service,
        build_launched_browser,
        build_reporting_service,
        build_schedule_gateway,
    )
    from scoutmb.ports.clock import MonotonicSleeper, SeededJitter

    scouts = build_ingest_service(
        sheet_name=config.sheet, include_adults=config.include_adults
    ).load(config.input)
    checkpoint_store = build_checkpoint_store(config.output / "checkpoint.json")
    # ONE RetryPolicy, shared between the AcquisitionService (per-request backoff) and
    # run_schedule_pipeline/run_batch (the cross-scout breaker) -- see pipeline.py's own
    # docstring on why this sharing is this caller's contract to uphold.
    retry_policy = RetryPolicy(
        sleeper=MonotonicSleeper(), jitter=SeededJitter(), breaker_threshold=BREAKER_THRESHOLD
    )

    async with build_launched_browser(headed=config.headed, channel=config.channel) as browser:
        gateway = build_schedule_gateway(browser, allow_dead_assets=config.allow_dead_assets)
        service = build_acquisition_service(gateway, retry_policy)
        return await run_schedule_pipeline(
            config,
            scouts=scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=build_reporting_service(),
            progress_callback=progress_callback,
            resume_event=resume_event,
        )


def main() -> int:
    config = parse_args()
    try:
        return asyncio.run(run(config))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run**

`SHIMMED_MODULES` is deliberately NOT touched here — it stays at `("pdf_to_scouts.py",)` from
Task B10.1. `scout_schedule_cli.py` still has real logic in its legacy-duplicate functions at
this point in the sequence (see this task's revision note above); arming it now would fail
immediately. That arming — and scout_schedule_cli.py's actual `test_shimmed_module_contains_no_
business_logic` pass — happens in Task B10.4, once those functions and their last callers are
gone.

```bash
uv run pytest tests/characterization/test_acquisition_matrix.py tests/parity/test_acquisition_parity.py tests/characterization/test_cli_sched_matrix.py tests/integration/test_acquisition_pipeline.py tests/architecture -q
```

- [ ] **Step 8: Commit**

```bash
git add scout_schedule_cli.py src/scoutmb/features/acquisition/pipeline.py src/scoutmb/features/acquisition/batch.py src/scoutmb/interfaces/cli/schedule.py src/scoutmb/interfaces/cli/composition.py tests/integration/test_acquisition_pipeline.py
git commit -m "refactor(cli): run_schedule_pipeline is pure DI; interfaces/cli/{composition,schedule}.py own all adapter construction for the schedule CLI path"
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
- Delete: `tests/characterization/test_desktop_matrix.py` — found by the same live-import-graph
  audit Task B10.4 runs (`rg -n '^\s*(import|from) run_app\b' tests --glob '*.py'`), and missed
  by this task's original file list entirely. Its own module docstring says it exists solely to
  characterize `run_app.py`'s `free_port`/`wait_until_ready`/`main` dispatch via
  `pytest.MonkeyPatch` against that module's own seams — there is no package code under test
  here, only legacy characterization, exactly like `test_interface_matrix.py` above. Confirm
  sub-plan 3's Task B9.1 (`run_app.py`'s port-zero rendezvous + `troop349` desktop entrypoint)
  actually landed a package-side equivalent for each `DESK-PORT-*`/`DESK-READY-*`/`DESK-MODE-*`
  case (the same coverage-diff discipline as Step 1, below) before deleting — do not delete on
  the assumption alone.
- Modify: `bootstrap/build.spec`, `bootstrap/source_sync.py` (drop the now-deleted files —
  full fix lands in Task B11.1; this task only removes the `ui/server.py`/`run_app.py`/`ui/`
  entries so the release build does not reference deleted paths in the interim)

**Acceptance Criteria:**
- [ ] Every `UI-ROUTE-*`/`UI-IMPORT-*` execution key that `test_interface_matrix.py` covered is
      covered by `tests/parity/test_local_web_parity.py` before the former is deleted — checked
      by diffing the two files' case-id coverage, not assumed
- [ ] Every `DESK-PORT-*`/`DESK-READY-*`/`DESK-MODE-*` execution key that
      `test_desktop_matrix.py` covered has a package-side equivalent (sub-plan 3's Task B9.1)
      before that file is deleted — checked by the same coverage-diff discipline, not assumed
- [ ] `troop349` (built in sub-plan 3) is the only way to launch the local UI after this task
- [ ] `uv run pytest -q` has no `ModuleNotFoundError`/`ImportError` for `ui`, `run_app`, or
      either deleted harness anywhere in the remaining suite

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

Do the same cross-reference for `test_desktop_matrix.py` against sub-plan 3's Task B9.1 package
tests:

```bash
grep -o 'case_id="DESK-[A-Z]*-[0-9]*"' tests/matrix/cases/desktop_cases.py | sort -u
```

**Do not proceed to deletion if any `DESK-*` case id has no package-side equivalent** — extend
sub-plan 3's own desktop-launcher tests first.

- [ ] **Step 2: Delete `run_app.py` and its exclusive characterization runner, in one commit**

```bash
git rm run_app.py tests/characterization/test_desktop_matrix.py
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

**Goal:** Remove the last two flat modules and their exclusive characterization runners. Task
B10.1 already proved `pdf_to_scouts.py` pure delegation; `scout_schedule_cli.py` becomes pure
delegation for the FIRST time within this task's own Step 6, once its Category A/B/C fixes have
cleared out every external caller of its remaining legacy-duplicate functions.

**Revision note (post-Codex review, fourth pass):** An independent review found this task's own
Acceptance Criteria claimed `scout_schedule_cli.py` already passed the shim shape check
"from B10.1/B10.2" — false. B10.2 only rewrites `process_scout`/`async_main`/`main`; nine other
top-level functions (`is_schedule_response`, `discover_name`, `annotate_requirement_statuses`,
`render_email_text`, `render_email_html`, `write_email_reports`,
`_assert_blank_identity_results_have_no_records`, `_assert_blank_identity_scouts_have_no_records`,
`_attendee_key_for` — plus `days_from_class_name`, pending Step 1's audit) still have real
`if`/`for`/`try` bodies at that point in the sequence and would trip the shape check directly.
`write_html_report` is a TENTH function that must also be deleted alongside them, though for a
different reason: its own body is already clean delegation (it would not itself trip the shape
check), but it calls `annotate_requirement_statuses` and
`_assert_blank_identity_results_have_no_records` directly — leaving it behind after deleting
those would be dead code with a dangling reference to a function that no longer exists. Every
one of these ten is a deliberately-kept legacy duplicate whose sole remaining callers are THIS
task's own Category B test-file deletions. Fixed by adding a new Step 6 that deletes these
now-orphaned function bodies and arms `SHIMMED_MODULES` with `scout_schedule_cli.py` HERE, after
Steps 2-5 clear their last callers — not in B10.2, where it was previously (and incorrectly)
claimed to already hold.

**Revision note (post-Codex review, third pass):** The original file list here covered only 6
characterization files plus 3 independently-found stragglers — a live import-graph audit
(`rg -n '^\s*(import|from)\s+(scout_schedule_cli|pdf_to_scouts|run_app)\b' tests tools --glob
'*.py'`) found **34 files total** still importing a flat module, not 9. The gap is closed below
by splitting every hit into three categories, verified individually (not guessed): **Category
A** — a mechanical import-source swap, confirmed safe because `scout_schedule_cli.py`/
`pdf_to_scouts.py` ALREADY re-export the exact symbol from the exact package location the test
would swap to (both flat modules are largely Form-1 re-export shims already, per their own
`# noqa: F401 - legacy public surface` import blocks — reading those blocks directly is how each
Category A swap below was confirmed, not assumed). **Category B** — a Slice-2a-era
characterization/parity file whose entire job was proving the package matches the (about to be
deleted) legacy module; once legacy retires there is nothing left for it to compare against, so
it deletes alongside its target. **Category C** — needs individual reading before any fix is
written, because either no drop-in package equivalent exists (a different call signature, e.g.
`build_missing_requirements(scouts)` vs. the package's `group_missing_requirements(annotated,
attendee_key_of=..., clean_description=...)`), or the file mixes real package-level test
coverage with one legacy-comparison import that needs a judgment call this plan cannot make
blind. **Do not fabricate a Category C fix — every Category C file gets an explicit read-first
step below, matching this task's own pre-existing Step 1 discipline for
`test_phase_a_gap_closure.py`.**

**Files:**
- Delete: `scout_schedule_cli.py`, `pdf_to_scouts.py`
- Delete (Category B — superseded characterization/parity, superseded once their legacy target
  is gone): `tests/characterization/test_acquisition_matrix.py`,
  `tests/characterization/test_artifact_matrix.py`, `tests/characterization/test_browser_matrix.py`,
  `tests/characterization/test_cli_sched_matrix.py`, `tests/characterization/test_input_matrix.py`,
  `tests/characterization/test_pdf_matrix.py`, `tests/characterization/test_platform_matrix.py`,
  `tests/characterization/test_process_scout.py`, `tests/characterization/test_requirement_matrix.py`,
  `tests/parity/test_atomic_parity.py`, `tests/parity/test_identity_parity.py`,
  `tests/parity/test_missing_selection.py`, `tests/parity/test_models_parity.py`,
  `tests/parity/test_numbering_parity.py`, `tests/parity/test_output_parity.py`,
  `tests/parity/test_reporting_service_status_parity.py`
- Delete (audit first, may keep a narrower package-only remainder instead of deleting wholesale):
  `tests/characterization/test_phase_a_gap_closure.py` (Step 1, pre-existing)
- Modify (Category A — mechanical import-source swap, Step 3):
  `tests/characterization/test_inputs_and_outputs.py`, `tests/characterization/test_requirement_path.py`,
  `tests/unit/test_atomic_write.py`, `tests/unit/test_identity.py`, `tests/harnesses/corpus.py`,
  the trivial half of `tests/unit/test_output_filenames.py` (its `attendee_filename_stem` import
  only — see Step 5 for the rest of that file)
- Modify (Category C — read fully before writing any fix, Step 5):
  `tests/unit/test_output_filenames.py` (its `cli.process_scout`/`cli.ScoutInput`/
  `cli.write_email_reports` usage — a non-trivial rewrite, since `process_scout`'s old
  4-positional-arg call does not match `AcquisitionService.process`'s keyword-only API),
  `tests/privacy/test_surface_policies.py`, `tests/privacy/test_shareable_projection.py`,
  `tests/unit/test_output_schemas.py`, `tests/unit/test_run_identity_scope.py`,
  `tests/characterization/test_inference.py`, `tests/unit/test_inference_identity.py`,
  `tools/gen_golden.py`, `tests/packaging/test_core_imports.py`
- Modify: `tests/factories/records.py` (imports `ClassRecord`/`RequirementRecord` from
  `scout_schedule_cli` today — a one-line import fix, not a deletion), `tests/vertical/test_legacy_flows.py`,
  `tests/performance/test_phase_a_baseline.py` (both drive `scout_schedule_cli.main`/`process_scout`/
  `async_main` directly today — repointed to the package pipeline, not deleted; see Step 2)
- Modify: `docs/superpowers/plans/2026-08-04-slice-2b-gateway-acquisition.md`'s
  `tests/parity/test_acquisition_parity.py` (Task B5.4, Step 3) already had its cross-import of
  `_normalize_raw_names`/`_project` from `test_acquisition_matrix.py` fixed by duplicating both
  helpers locally — that file is one of this task's Category B deletions, so the cross-import
  would otherwise break collection the moment this task's deletion commit lands
- Modify: `bootstrap/build.spec`, `bootstrap/source_sync.py` (drop the remaining flat-file
  entries; Task B11.1 replaces them with the package sync)
- Modify: `pyproject.toml` (remove nothing — the three console scripts already point at package
  modules; only `[tool.ruff] extend-exclude` and mypy's `files` omission lists lose these two
  entries, since there is no longer a flat module to exclude)
- Modify (Step 6, NEW this pass): `scout_schedule_cli.py` (delete `is_schedule_response`,
  `discover_name`, `annotate_requirement_statuses`, `render_email_text`, `render_email_html`,
  `write_email_reports`, `write_html_report`, `_assert_blank_identity_results_have_no_records`,
  `_assert_blank_identity_scouts_have_no_records`, `_attendee_key_for` — and `days_from_class_
  name`, pending Step 1's read of `test_phase_a_gap_closure.py` — now that Steps 2-5 have removed
  their last external callers), `tests/architecture/test_dependency_rules.py` (`SHIMMED_MODULES`
  gains `"scout_schedule_cli.py"`, moved here from Task B10.2 where it was previously and
  incorrectly armed too early)

**Acceptance Criteria:**
- [ ] `pdf_to_scouts.py` passes `test_shimmed_module_contains_no_business_logic` immediately
      before its deletion (already true from B10.1 — re-verify, don't re-assume)
- [ ] `scout_schedule_cli.py` passes `test_shimmed_module_contains_no_business_logic` immediately
      before its deletion — proven TRUE for the first time by this task's own Step 6, not
      inherited from an earlier task
- [ ] Every one of the ~10 deleted legacy-duplicate functions is re-verified (via `rg`, not
      assumed) to have zero remaining callers outside `scout_schedule_cli.py` itself before its
      body is deleted
- [ ] Every execution key the deleted Category B characterization/parity files drove has a
      passing package-side parity runner already covering it (same audit discipline as Task
      B10.3's Step 1) — checked per file, not assumed from the category label alone
- [ ] Every Category A import swap is verified against the flat module's OWN current re-export
      block (its `# noqa: F401 - legacy public surface` import lines) before being written, not
      assumed to exist because the symbol name sounds familiar
- [ ] No Category C file is touched without first being read in full — its actual fix (rewrite,
      narrow, or delete-as-redundant) is written only after that read, following Step 1's
      existing precedent for `test_phase_a_gap_closure.py`
- [ ] `tests/factories/records.py`, `tests/vertical/test_legacy_flows.py`, and
      `tests/performance/test_phase_a_baseline.py` — all three found by an independent review to
      import the flat modules directly — are fixed **before** deletion, not discovered broken
      after
- [ ] `troop349-pdf`/`troop349-schedule` are the only remaining ways to run the two pipelines
- [ ] `uv run pytest -q` collects cleanly with zero references to either deleted module —
      verified by re-running the same `rg` audit this task's revision note used, expecting zero
      hits, not merely by running the suite once and hoping nothing surfaced

**Verify:** `uv run pytest -q` → PASS (no collection errors); AND
`rg -n '^\s*(import|from)\s+(scout_schedule_cli|pdf_to_scouts|run_app)\b' tests tools src
--glob '*.py'` → zero hits

**Recovery:** `git revert` this commit per module — deleting `scout_schedule_cli.py` and
`pdf_to_scouts.py` are two separate commits, so either can be reverted independently. The
Category A/C fix commits (Steps 3 and 5) and Step 6's dead-function-deletion-plus-shim-arming
commit are each separate from both deletion commits and independently revertable too.

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
drive `scout_schedule_cli.main`/`process_scout`/`async_main` directly through a strict-fake
`async_playwright` monkeypatch against `scout_schedule_cli.py`'s OWN top-level `async_playwright`
name.

**Read both files in full before re-pointing them — Task B10.2 (above) changed WHERE a
monkeypatch target even exists, so the old plan of "just re-point the entry-point call" is no
longer sufficient on its own:**

- `run_schedule_pipeline` (Task B10.2, Step 3) is now pure dependency injection — it has NO
  `async_playwright` import anywhere, at any scope, so there is nothing left to monkeypatch on
  it. A test driving `run_schedule_pipeline` directly should construct a `StrictFakeBrowser`,
  wrap it in `PlaywrightScoutingEventGateway`/`AcquisitionService` exactly like
  `tests/integration/test_acquisition_pipeline.py`'s new tests do, and call
  `run_schedule_pipeline(config, scouts=..., service=..., retry_policy=..., checkpoint_store=...,
  reporting_service=...)` directly — no monkeypatch needed at all. This is the right target for
  assertions that characterize the PIPELINE's behavior (request counts, growth bounds) rather
  than argv parsing or process exit codes.
- `interfaces/cli/composition.py`'s `build_launched_browser` (Task B10.2, Step 4) imports
  `async_playwright` FUNCTION-LOCAL, inside the function body — following this codebase's own
  established capability-guard precedent (`adapters/pdf/extract.py`'s `_import_pdf_stack()`,
  which does the same for `cv2`/`fitz`/`numpy`). There is deliberately no module-level
  `async_playwright` attribute on `composition.py` to `monkeypatch.setattr(...)` against. A test
  that specifically needs to exercise `interfaces.cli.schedule.main()`/`run()` end to end
  (argv parsing, real exit-code mapping) either needs a real (even if trivial/headless) browser
  launch, or needs `build_launched_browser` itself replaced. **The correct patch target is
  `monkeypatch.setattr("scoutmb.interfaces.cli.composition.build_launched_browser", fake)` — the
  function's SOURCE module, not `scoutmb.interfaces.cli.schedule`.** `run()`'s own
  `from scoutmb.interfaces.cli.composition import (..., build_launched_browser, ...)` (Task
  B10.2, Step 6) is a FUNCTION-LOCAL import executed fresh every time `run()` is called, so it
  looks up whatever `composition.build_launched_browser` currently is at call time — patching
  `composition`'s own attribute before invoking `run()` is picked up correctly.
  `monkeypatch.setattr("scoutmb.interfaces.cli.schedule.build_launched_browser", fake)` does
  NOT work: that name is never bound at `schedule.py`'s MODULE level at all (only as a local
  variable inside `run()`'s function scope, after it has already been called), so `monkeypatch`
  would raise `AttributeError` trying to find it on that module.
- `scout_schedule_cli.process_scout` is UNCHANGED by this refactor beyond its own shim body
  (Task B10.2, Step 5) — it constructs its own gateway/browser inline, never calls `run()`, and
  `scout_schedule_cli.py`'s own top-level `async_playwright` import is untouched, so any
  existing monkeypatch against THAT specific name, for tests deliberately characterizing the
  flat script's `process_scout` entry point rather than the package pipeline, keeps working with
  no change required. `scout_schedule_cli.main` is now a pure re-export of
  `scoutmb.interfaces.cli.schedule.main` (Task B10.2, Step 5's revised main-becomes-re-export
  fix) — `scout_schedule_cli.main` and `scoutmb.interfaces.cli.schedule.main` are the literal
  same function object, so a test exercising either name behaves identically and either
  monkeypatch target above (composition's `build_launched_browser`) applies the same way.
  `scout_schedule_cli.async_main`'s shim body calls `interfaces.cli.schedule.run()` directly, so
  a test driving `async_main` end to end also picks up a `composition.build_launched_browser`
  monkeypatch transitively through that call, with no separate patch target needed for it.

Pick per-test, after reading each test's actual assertions, which of the three above it needs —
do not blanket-apply one strategy to both files. The assertions themselves (request counts,
growth bounds, the five-stage wiring) should not need to change, since they characterize
behavior, not which module happens to expose it. Do not delete either file: they hold real,
non-redundant coverage (a genuine multi-stage PDF→schedule→report wire-up, and deterministic
request-count/growth-bound assertions) that no other test in this plan reproduces.

```bash
git add tests/factories/records.py tests/vertical/test_legacy_flows.py tests/performance/test_phase_a_baseline.py
git commit -m "fix(tests): repoint the three tests an independent review found still importing the flat modules"
```

- [ ] **Step 3: Fix every Category A file — mechanical import-source swaps**

Each swap below was confirmed against the flat module's own current re-export block (its
`# noqa: F401 - legacy public surface` import lines) before being written here — every symbol
below is already a straight re-export at the exact package location shown, not a guess.

```python
# tests/characterization/test_inputs_and_outputs.py -- replace the top import
from scoutmb.adapters.files.atomic import write_csv
from scoutmb.core.models import ClassRecord, RequirementRecord
```

```python
# tests/characterization/test_requirement_path.py -- replace the top import
from scoutmb.core.inference.numbering import requirement_path
```

```python
# tests/unit/test_atomic_write.py -- replace BOTH imports
from scoutmb.adapters.files.atomic import atomic_write_text
# ... and, further down where ExtractedAttendee/write_attendees_csv are imported:
from scoutmb.core.models import ExtractedAttendee
from scoutmb.features.ingest.pdf_extract import write_attendees_csv
```

> `atomic_write_text` exists in TWO package locations
> (`scoutmb.adapters.files.atomic` and `scoutmb.features.ingest.pdf_extract`, the latter
> presumably a re-export or thin wrapper of the former). This test currently exercises it via
> `scout_schedule_cli`'s re-export, which itself points at `scoutmb.adapters.files.atomic`
> (confirmed at that flat module's own import block) — use that one, not the `pdf_extract` one,
> to match what was actually being tested before this swap.

```python
# tests/unit/test_identity.py -- replace the top import
from scoutmb.core.identity import AttendeeId, MissingAttendeeId, RunIdentity
```

```python
# tests/harnesses/corpus.py -- replace the function-local import
from scoutmb.adapters.pdf.pages import extract_pdf
```

```python
# tests/unit/test_output_filenames.py -- fix ONLY the attendee_filename_stem import here;
# the `cli.process_scout`/`cli.ScoutInput`/`cli.write_email_reports` usage elsewhere in this
# file is Category C -- see Step 5, do not touch it in this commit.
from scoutmb.core.identity import attendee_filename_stem
```

```bash
uv run pytest tests/characterization/test_inputs_and_outputs.py tests/characterization/test_requirement_path.py tests/unit/test_atomic_write.py tests/unit/test_identity.py tests/private_corpus/test_authentic.py -q
git add tests/characterization/test_inputs_and_outputs.py tests/characterization/test_requirement_path.py tests/unit/test_atomic_write.py tests/unit/test_identity.py tests/harnesses/corpus.py tests/unit/test_output_filenames.py
git commit -m "fix(tests): repoint Category A flat-module imports at their existing package equivalents"
```

> `tests/harnesses/corpus.py` has no tests of its own to run directly — it is imported by
> `tests/private_corpus/test_authentic.py` (and `tests/plugins/matrix_gate.py`), so that
> consuming test is what actually exercises the swapped `extract_pdf` import.

- [ ] **Step 4: Delete every Category B file — superseded characterization/parity coverage**

Each of these characterizes ONLY the legacy module being deleted (a `LegacyXRunner`/`import
scout_schedule_cli as legacy` comparison against a package runner that already has its own
independent test elsewhere) — read each file's own module docstring to confirm this before
deleting, the same way `test_acquisition_matrix.py`/`test_pdf_matrix.py`'s docstrings already
state it plainly for the two files the original file list already covered.

```bash
git rm \
  tests/characterization/test_artifact_matrix.py \
  tests/characterization/test_input_matrix.py \
  tests/characterization/test_platform_matrix.py \
  tests/characterization/test_requirement_matrix.py \
  tests/parity/test_atomic_parity.py \
  tests/parity/test_identity_parity.py \
  tests/parity/test_missing_selection.py \
  tests/parity/test_models_parity.py \
  tests/parity/test_numbering_parity.py \
  tests/parity/test_output_parity.py \
  tests/parity/test_reporting_service_status_parity.py
git commit -m "chore(tests): retire Category B parity/characterization tests superseded by the retirement plan"
```

- [ ] **Step 5: Read and fix every Category C file — no fabricated fixes**

Read each file in full before writing its fix. None of these are pre-written here, on purpose —
inventing a fix for a file this plan has not read is exactly the failure mode this whole
revision pass exists to catch (see this task's revision note). For each:

- `tests/unit/test_output_filenames.py` — its `cli.process_scout(browser, scout, args,
  tmp_path)` call uses the OLD 4-positional-arg signature; `AcquisitionService.process` is
  keyword-only (`scout=`, `config=`, `raw_dir=`, `run_identity=`) and returns via a gateway, not
  a bare `Browser`. Decide whether this file's remaining assertions (`cli.write_email_reports`,
  `cli.ScoutInput`) are about filename generation specifically (in which case they may not need
  `process_scout` at all) or genuinely need the acquisition call — rewrite accordingly.
- `tests/privacy/test_surface_policies.py` — 12 `scout_schedule_cli` sites plus 1
  `pdf_to_scouts` site; likely a mix of Category A-shaped swaps and assertions that need a real
  package call site. Read every site individually; do not blanket-swap.
- `tests/privacy/test_shareable_projection.py` — 4 sites.
- `tests/unit/test_output_schemas.py` — a real package unit-test file with ONE function-scoped
  `import scout_schedule_cli as legacy` for a comparison assertion; decide whether that
  comparison becomes a hardcoded expected value or an assertion against a still-live package
  equivalent.
- `tests/unit/test_run_identity_scope.py` — same shape as `test_output_schemas.py` above.
- `tests/characterization/test_inference.py` and `tests/unit/test_inference_identity.py` — both
  import `build_missing_requirements` from `scout_schedule_cli`, which has NO drop-in package
  equivalent: `scoutmb.core.inference.missing.group_missing_requirements` takes
  `attendee_key_of`/`clean_description` as INJECTED CALLABLES, a different signature, not a
  rename. Compare each file's actual assertions against `tests/unit/test_inference_missing.py`/
  `test_inference_status.py`/`test_inference_tree.py` (if those exist and already cover the
  package function) before deciding whether this file migrates or is redundant and deletes.
- `tools/gen_golden.py` — a golden-file generation tool, not a test; read its actual usage of
  `scout_schedule_cli` before deciding whether it re-points at the package or retires alongside
  the flat module (if its sole purpose was generating goldens FROM the legacy path).
- `tests/packaging/test_core_imports.py` — 3 sites testing the optional-dependency capability
  guard; deleting `pdf_to_scouts.py` changes what this file can even test (a bare `import
  pdf_to_scouts` failing due to a missing optional dependency won't exist as a scenario once
  that module is gone) — read what it is actually asserting before deciding whether it needs a
  new target module or is itself obsoleted by the deletion.

```bash
git add <whichever Category C files were fixed this pass>
git commit -m "fix(tests): repoint Category C flat-module imports after individual review"
```

- [ ] **Step 6: Delete `scout_schedule_cli.py`'s remaining dead legacy-duplicate functions, then
      arm the shim shape check**

Independently found (this revision): Task B10.2's `process_scout`/`async_main`/`main` rewrites
alone are not enough for `scout_schedule_cli.py` to pass `test_shimmed_module_contains_no_
business_logic` — nine other top-level functions still have real `if`/`for`/`try` bodies
(`is_schedule_response`, `discover_name`, `annotate_requirement_statuses`, `render_email_text`,
`render_email_html`, `write_email_reports`, both `_assert_blank_identity_*` helpers,
`_attendee_key_for`; `days_from_class_name` pending Step 1's audit). `write_html_report` is a
tenth that must be deleted alongside them for a DIFFERENT reason — its own body is already clean
delegation and would not itself trip the check, but it calls `annotate_requirement_statuses` and
`_assert_blank_identity_results_have_no_records` directly, so leaving it in place after deleting
those would be dead code with a dangling reference. Every one of them is a deliberately-kept
legacy duplicate whose own docstring says it exists ONLY so a specific characterization test
could compare it against its package equivalent. Now that Steps 2-5 above have fixed or deleted
every file that imported `scout_schedule_cli` directly, these functions' LAST remaining callers
are gone too. Re-verify before deleting — don't assume the list below is still exhaustive after
Steps 2-5's actual edits:

```bash
rg -n '\b(is_schedule_response|discover_name|annotate_requirement_statuses|render_email_text|render_email_html|write_email_reports|write_html_report|_assert_blank_identity_results_have_no_records|_assert_blank_identity_scouts_have_no_records|_attendee_key_for|days_from_class_name)\b' tests tools ui src --glob '*.py' | grep -v '^scout_schedule_cli.py'
```

Expected: zero hits outside `scout_schedule_cli.py` itself (`days_from_class_name`'s fate
depends on how Step 1 resolved `test_phase_a_gap_closure.py` — confirm it before including or
excluding that one). If the command finds a live caller Steps 2-5 didn't account for, fix that
caller first — do not delete the function it depends on out from under it.

Delete `is_schedule_response`, `discover_name`, `annotate_requirement_statuses`,
`render_email_text`, `render_email_html`, `write_email_reports`, `write_html_report`,
`_assert_blank_identity_results_have_no_records`, `_assert_blank_identity_scouts_have_no_records`,
`_attendee_key_for` (and `days_from_class_name`, if the `rg` check confirms it's clear) from
`scout_schedule_cli.py` entirely — not shim them, DELETE the definitions, since nothing calls
them anymore. Then arm the shape check and confirm it actually passes:

```python
# tests/architecture/test_dependency_rules.py
SHIMMED_MODULES: tuple[str, ...] = ("pdf_to_scouts.py", "scout_schedule_cli.py")
```

```bash
uv run pytest tests/architecture -k shimmed_module -v
```

Expected: PASS. If it still fails, the `rg` re-verification above missed a real caller or a
function this list didn't capture — re-run the full-file AST check
(`python3 -c "import ast; ..."` style, walking only each top-level function's `.body`, not the
whole node) against `scout_schedule_cli.py` directly to find exactly what's left, rather than
guessing.

```bash
git add scout_schedule_cli.py tests/architecture/test_dependency_rules.py
git commit -m "chore: delete scout_schedule_cli.py's remaining dead legacy-duplicate functions; arm the shim shape check"
```

- [ ] **Step 7: Re-verify the shape check, then delete `pdf_to_scouts.py`**

```bash
uv run pytest tests/architecture -k shimmed_module -v
git rm pdf_to_scouts.py tests/characterization/test_pdf_matrix.py tests/characterization/test_browser_matrix.py
git commit -m "chore: retire pdf_to_scouts.py"
```

- [ ] **Step 8: Delete `scout_schedule_cli.py`, in its own commit**

```bash
git rm scout_schedule_cli.py tests/characterization/test_acquisition_matrix.py tests/characterization/test_cli_sched_matrix.py tests/characterization/test_process_scout.py
git commit -m "chore: retire scout_schedule_cli.py"
```

- [ ] **Step 9: Update the remaining build/lint config**

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

- [ ] **Step 10: Run and commit**

```bash
uv run pytest -q
rg -n '^\s*(import|from)\s+(scout_schedule_cli|pdf_to_scouts|run_app)\b' tests tools src --glob '*.py'
```

Both commands must confirm a clean state — the `pytest` run collects with zero errors, and the
`rg` audit returns zero hits — before this commit.

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
  real cancellation maps to `CANCEL`/`CANCELLED`, never `FAIL`. It is pure dependency injection —
  no adapter import, no import from `scoutmb.interfaces` — with every adapter for the schedule
  CLI path (the launched browser, gateway, checkpoint store, reporting service) constructed by
  `interfaces/cli/composition.py`'s builders and `interfaces/cli/schedule.py`'s `run()`.
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
