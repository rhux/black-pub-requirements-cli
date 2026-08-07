# Slice 2b.3 — Web Boundary & Interface Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Revision note (post-Codex review):** An earlier draft of this plan had a real oracle-invariant
> violation — it guarded `generate_emails`'s `scouts.json` read, silently changing `UI-ROUTE-021`
> (a `PRESERVE` case pinning today's 500-on-corrupt-input crash) with no sanctioned exception.
> That fix is removed; `open_report`'s `summary.json` guard stays (nothing pins its crash). Also
> fixed: `_client_for()` in the parity tests used bare `httpx.ASGITransport`, which does not run
> FastAPI's lifespan — every route reading `request.app.state` would have raised
> `AttributeError` before any assertion ran; `UiSettings` moved to `scoutmb.config` (sub-plan 2)
> instead of a new `scoutmb.ui_settings` module the dependency-edge table doesn't recognize;
> `open_folder`'s blocking `subprocess.run`/`os.startfile` call is now wrapped in
> `asyncio.to_thread` inside its async route; the rendezvous test now actually starts a server on
> the bound socket rather than only proving the socket is bindable; and the entrypoint parity
> task's acceptance criteria no longer claim untested coverage (a real `KeyboardInterrupt`/handled
> -exception test was added, narrowed to what a subprocess check can actually prove).

**Goal:** Fix the four characterized UI defects directly on the still-live `ui/server.py` (landing
`UI-ROUTE-023`/`UI-ROUTE-030`), then build the package's `create_app(settings)` lifespan factory
with a `JobRegistry` that retains every background task (landing `UI-IMPORT-001`), compose all
three interfaces (CLI/web/desktop) behind it, and remove `run_app.py`'s bind-close-rebind race.

**Architecture:** `ui/server.py` keeps its exact `busy`/`current_download`/`operations` module
globals — the frozen `UI-ROUTE-024..029` characterization cases read those globals directly
(`tests/characterization/test_interface_matrix.py:490-544` does `module.busy["pdf-extract"]`),
so this sub-plan does not touch that mechanism. The package's `create_app` in
`src/scoutmb/interfaces/web/` is a parallel, additive implementation — same routes, same
externally-observable HTTP behavior, built on sub-plan 2's `JobSupervisor`/`RunStateMachine`
internally — proven equivalent by a parity test, exactly like every other 2a/2b domain. `ui/server.py`
itself retires in sub-plan 4 (B10), once the package route runner covers every case it holds.

**Tech Stack:** FastAPI, `httpx.AsyncClient` + `ASGITransport` (already the test harness's
pattern), `uvicorn`, `pywebview`, the `JobSupervisor`/`RunStateMachine` from sub-plan 2
(`2026-08-05-slice-2b-config-run-state.md` — this sub-plan depends on that one merging first).

**Global Constraints:**
- `UI-ROUTE-024` through `UI-ROUTE-029` (all `Classification.PRESERVE`) must keep passing
  **unmodified** — this sub-plan never edits `ui/server.py`'s `busy`/`current_download`/
  `operations` globals or the observable shape the legacy runner reads off them.
- `UI-ROUTE-023` and `UI-ROUTE-030` (both `Classification.INTENTIONAL_CHANGE`, `target_owner=
  "Slice 2"`) are fixed **directly on `ui/server.py`**, not only in a parallel package copy —
  the characterization test that pins them drives `ui.server.app` itself, so a fix that exists
  only in an as-yet-unused package module would not make either case's `expected_by_context`
  update true.
- The package `create_app(settings)` route surface is built and parity-tested **after** the
  `ui/server.py` defect fixes land, so it is built to match the already-corrected behavior rather
  than needing a second pass.
- `troop349`/`troop349-schedule` console scripts match their flat-script predecessors
  argument-for-argument, exit-code-for-exit-code, byte-for-byte on stdout/stderr, tested as
  **installed subprocesses** run from outside the repository — calling `main()` in-process does
  not exercise the same code path (per the Phase B spec's own note on why this matters).

**User decisions (already made):** Split slice 2b into four independent sub-plans by subsystem;
this sub-plan covers B8 (web boundary) + B9 (compose/rendezvous) only.

**Design decisions this sub-plan makes** (flagged for review before execution):

1. **`ui/server.py`'s defect fixes and the package route surface are two separate tasks in a
   fixed order** (fix legacy first, mirror second) — see Global Constraints above for why.
2. **The package web app lives at `src/scoutmb/interfaces/web/app.py` + `routes.py` +
   `composition.py`**, mirroring the existing `interfaces/cli/{pdf.py, composition.py}` split:
   `routes.py` holds route handlers (features/ports only), `composition.py` is the sole module
   permitted to import adapters, `app.py` is the `create_app(settings)` factory that wires them.
3. **`JobRegistry` in this sub-plan is `runtime.jobs.JobSupervisor` under a web-facing name** —
   the Phase B spec's package layout table calls it `JobRegistry`; sub-plan 2 already built the
   identical mechanism as `JobSupervisor` (retain-every-task, cancel-and-await-on-shutdown). Rather
   than build a second class, `app.state.job_registry` in this sub-plan **is** a `JobSupervisor`
   instance — the name in code is `job_registry: JobSupervisor` to read naturally at call sites.

---

## Task B8.1: `create_app(settings)` factory — zero import-time I/O

**Goal:** A lifespan factory that constructs its own `UiSettings`, `JobSupervisor`, and FastAPI
`app` fresh per call — nothing at module import time touches the filesystem, the network, or
starts a task. Health check only; the rest of the route surface is Task B8.3.

**Files:**
- Create: `src/scoutmb/interfaces/web/__init__.py`, `src/scoutmb/interfaces/web/app.py`
- Test: `tests/integration/test_app_lifespan.py`

**Acceptance Criteria:**
- [ ] Importing `scoutmb.interfaces.web.app` performs no filesystem/network I/O and starts no
      task — proven by importing it in a subprocess with a poisoned `SCOUTMB_DATA_DIR` that would
      fail if anything touched it, and asserting the import itself doesn't raise
- [ ] `create_app(settings)` returns a distinct `FastAPI` instance on every call (no shared
      module-level `app` singleton)
- [ ] `app.state.job_registry` is a `JobSupervisor`; the lifespan's shutdown phase calls
      `job_registry.shutdown()`
- [ ] `GET /api/health` returns `{"status": "ok"}`

**Verify:** `uv run pytest tests/integration/test_app_lifespan.py -q` → PASS

**Recovery:** Leave `create_app` unreferenced; `ui/server.py`'s module-level `app` stays the only
served application.

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/integration/test_app_lifespan.py
"""UI-IMPORT-001: create_app(settings) has no import-time side effects and constructs a fresh
app + JobSupervisor per call. The subprocess import-probe pattern mirrors
tests/harnesses/subprocess.py::run_import_probe (the Phase B spec's own reference
implementation) rather than reusing PYTHONPATH under python -I, which -I ignores.

Lifespan is driven through Starlette's own `app.router.lifespan_context(app)` async context
manager -- the exact mechanism both `asgi-lifespan`'s LifespanManager and Starlette's own
TestClient use internally -- rather than a third-party dependency (`asgi-lifespan` is not a
project dependency; confirmed by grepping pyproject.toml) or plain httpx.ASGITransport, which
does NOT run lifespan on its own. An earlier draft of this test file used ASGITransport alone
and would have reached routes before app.state.settings/job_registry were ever set."""

from __future__ import annotations

import subprocess
import sys

import httpx
import pytest

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app


def test_import_has_no_side_effects_in_a_poisoned_environment(tmp_path) -> None:
    poisoned_data_dir = tmp_path / "does-not-exist-and-must-stay-that-way"
    probe = (
        "import sys; sys.path.insert(0, %r)\n"
        "import scoutmb.interfaces.web.app\n"
        "print('IMPORT_OK')\n"
    ) % str(__import__("pathlib").Path.cwd() / "src")
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        env={"SCOUTMB_DATA_DIR": str(poisoned_data_dir)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
    assert not poisoned_data_dir.exists(), "import must not have created the data root"


def test_create_app_returns_a_fresh_instance_each_call(tmp_path) -> None:
    settings_a = UiSettings(data_root=tmp_path / "a")
    settings_b = UiSettings(data_root=tmp_path / "b")
    app_a = create_app(settings_a)
    app_b = create_app(settings_b)
    assert app_a is not app_b


@pytest.mark.anyio
async def test_health_and_lifespan_shutdown(tmp_path) -> None:
    settings = UiSettings(data_root=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert hasattr(app.state, "job_registry")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
```

Run: `uv run pytest tests/integration/test_app_lifespan.py -v` → FAIL (module doesn't exist)

- [ ] **Step 2: Write the factory**

`UiSettings` already lives in `scoutmb.config` (sub-plan 2's Task B6) — this task only imports
it, it does not create a new module for it.

```python
# src/scoutmb/interfaces/web/__init__.py
```

```python
# src/scoutmb/interfaces/web/app.py
"""create_app(settings) -- UI-IMPORT-001: importing this module performs no filesystem,
network, or job side effects. Every side-effecting call (ensure_dirs, JobSupervisor
construction, route registration) happens INSIDE create_app or the lifespan, never at module
scope. Contrast with ui/server.py, which still does all of this at import time -- that stays
true intentionally until Slice 2b retires it (sub-plan 4), since UI-ROUTE-024..029 read its
module globals directly.

settings.ensure_dirs() is called HERE, synchronously, not only inside the lifespan -- Task
B10.0 (sub-plan 4) mounts StaticFiles(directory=settings.runs_dir) inside this same function,
and Starlette's StaticFiles constructor checks directory existence immediately, before the
lifespan (which runs later, only once something actually starts serving/tests the app) ever
gets a chance to create it. Calling ensure_dirs() here as well closes that ordering gap; it is
cheap and idempotent, so calling it twice (here and in the lifespan) costs nothing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from scoutmb.config import UiSettings
from scoutmb.runtime.jobs import JobSupervisor


def create_app(settings: UiSettings) -> FastAPI:
    settings.ensure_dirs()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.job_registry = JobSupervisor()
        try:
            yield
        finally:
            await app.state.job_registry.shutdown()

    app = FastAPI(title="Troop 349 Summer Camp Command Program UI", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/integration/test_app_lifespan.py tests/characterization/test_interface_matrix.py -q
```

```bash
git add src/scoutmb/interfaces/web tests/integration/test_app_lifespan.py
git commit -m "feat(web): add create_app(settings) factory with zero import-time side effects"
```

---

## Task B8.2: Fix the four UI defects on `ui/server.py` directly

**Goal:** Land `UI-ROUTE-023` (cross-platform folder open) and `UI-ROUTE-030` (validate
`html_report` before use) on the live module, plus two of the silent bugs the Phase B spec names
alongside them: the PDF-upload cleanup unlink without an `is_file()` guard, and `open_report`'s
unguarded persisted-JSON read. **`generate_emails`'s `scouts.json` read is deliberately left
unguarded** — see Design Note below; an earlier draft of this task guarded it and that was a
real defect this revision removes.

**Design note (post-Codex review): `generate_emails`'s crash-on-corrupt-`scouts.json` is a
`PRESERVE` case, not a silent bug.** `UI-ROUTE-021` pins today's behavior exactly:
`tests/characterization/test_interface_matrix.py:157`'s own comment says
"`UI-ROUTE-021`/`UI-ROUTE-023` pin exactly this for two routes that currently have no
route-level try/except" — `UI-ROUTE-023` is the sanctioned one (`INTENTIONAL_CHANGE`,
`target_owner="Slice 2"`); `UI-ROUTE-021` is **not**, and has no target_owner at all. Guarding
`generate_emails`'s read (an earlier draft of this task did exactly that) would silently change
a `PRESERVE` case's observed status from 500 to 400 — an undeclared seventh exception to the
spec's six sanctioned rows (`spec:467`). `open_report`'s `summary.json` read has no such case
pinning its crash — confirmed by the same comment naming only two routes — so guarding *that*
read is safe, uncharacterized-but-permitted hardening, not a violation.

**Files:**
- Modify: `ui/server.py` (`start_pdf_extract`, `open_report`, `open_emails_folder`)
- Modify: `tests/matrix/cases/interface_cases.py` (`UI-ROUTE-023`/`UI-ROUTE-030`'s
  `expected_by_context`; bump the digest in the same commit)
- Modify: `tests/characterization/test_interface_matrix.py` (`_route_UI_ROUTE_023`/
  `_route_UI_ROUTE_030` runner methods — driving mechanics change, not oracle data; see Step 1)

**Acceptance Criteria:**
- [ ] `start_pdf_extract`'s upload-directory cleanup only unlinks entries that are files
      (`is_file()` guard); a stray subdirectory in `pdf-uploads/` no longer crashes the route
- [ ] `open_emails_folder` dispatches on `sys.platform` through a **named, mockable** module-level
      function (`open_folder`) — not an inline `subprocess.run` call the test suite would have to
      actually execute to exercise, which would launch a real GUI file-manager window during an
      automated test run
- [ ] `open_report` rejects any `html_report` value that is not a bare filename resolving inside
      `RUNS_DIR/<run_id>` **before** constructing a URL or calling `webbrowser.open` — no
      path-traversal segment ever reaches either
- [ ] `open_report`'s existing `webbrowser.open` call is **preserved** for a valid `html_report`
      (this is `UI-ROUTE-018`'s `Classification.PRESERVE` behavior — the fix must not touch it)
- [ ] `open_report`'s `summary.json` read is guarded against malformed JSON, returning a clean
      400 rather than an unhandled 500 (`list_runs` already guards its own read — confirmed by
      reading its current body; no change needed there)
- [ ] `generate_emails`'s `scouts.json` read remains **unguarded** — `UI-ROUTE-021` must keep
      passing unmodified, still observing a 500 on corrupt input
- [ ] `UI-ROUTE-023` and `UI-ROUTE-030`'s `expected_by_context` updated to the new behavior;
      digest bumped in the same commit

**Verify:** `uv run pytest tests/characterization/test_interface_matrix.py tests/matrix -q` → PASS

**Recovery:** Revert each fix independently — they touch different routes and do not depend on
each other; `git revert` the specific commit for the one defect found to regress something.

**Steps:**

- [ ] **Step 1: Extract `open_folder` so the platform dispatch is mockable, and update the two
  runner methods + case expectations together**

`_route_UI_ROUTE_023` (`tests/characterization/test_interface_matrix.py:467-471`) drives
`open_emails_folder` with **no mock of any kind** today, because today's bug (a bare
`os.startfile` call) is expected to raise `AttributeError` on non-Windows Python before it would
ever need one. Once the route dispatches on `sys.platform`, running the fixed code un-mocked
would invoke a real `subprocess.run(["open"/"xdg-open", ...])` — actually launching a GUI file
manager during an automated test. The fix therefore extracts the platform dispatch into a named
module-level function and has the test monkeypatch it, mirroring the *exact* pattern
`UI-ROUTE-018` already uses for `module.webbrowser.open` two functions below it in the same file.

```python
# tests/characterization/test_interface_matrix.py -- replace _route_UI_ROUTE_023 (lines 467-471)
    async def _route_UI_ROUTE_023(self, module, client) -> InterfaceObservation:
        opened_paths: list[str] = []
        self.monkeypatch.setattr(module, "open_folder", lambda path: opened_paths.append(str(path)))
        run_dir = module.RUNS_DIR / "2026-07-23_1200"
        (run_dir / "emails").mkdir(parents=True)
        resp = await client.post("/api/runs/2026-07-23_1200/open-emails-folder")
        assert opened_paths, "open_folder was never called"
        return InterfaceObservation(status=resp.status_code, body={"opened": (await resp.json()).get("opened")})
```

`UI-ROUTE-030`'s fix is narrower: `open_report` already routes a valid `html_report` through
`webbrowser.open`, unchanged (`UI-ROUTE-018` keeps passing as-is) — only the **malicious** input
now gets rejected before `webbrowser.open` is ever reached, so `opened` (the existing
`_record_open` recorder this runner method already builds) stays empty instead of receiving the
unsanitized URL:

```python
# tests/characterization/test_interface_matrix.py -- replace _route_UI_ROUTE_030 (lines 578-592)
    async def _route_UI_ROUTE_030(self, module, client) -> InterfaceObservation:
        opened: list[str] = []

        def _record_open(url: str) -> bool:
            opened.append(url)
            return True

        module.webbrowser.open = _record_open
        self._write_summary(module, "2026-07-23_1200", {"html_report": "../../elsewhere/evil.html"})
        resp = await client.post("/api/runs/2026-07-23_1200/open-report")
        return InterfaceObservation(status=resp.status_code, body={"webbrowser_open_called": bool(opened)})
```

```python
# tests/matrix/cases/interface_cases.py -- UI-ROUTE-023, replace expected_by_context
# (classification/target_owner/target_observation stay -- they describe what changed and why;
# only the OBSERVED value changes, matching the sanctioned-exception pattern used throughout
# this plan for every other landed intentional-change row)
        expected_by_context={"route": InterfaceObservation(status=200, body={"opened": True})},
```

```python
# tests/matrix/cases/interface_cases.py -- UI-ROUTE-030, replace expected_by_context
        expected_by_context={
            "route": InterfaceObservation(status=400, body={"webbrowser_open_called": False})
        },
```

- [ ] **Step 2: `start_pdf_extract`'s unlink guard**

```python
# ui/server.py -- start_pdf_extract, replace the cleanup loop
    if PDF_UPLOADS_DIR.exists():
        for stale in PDF_UPLOADS_DIR.iterdir():
            if stale.is_file():
                stale.unlink()
    else:
        PDF_UPLOADS_DIR.mkdir(parents=True)
```

- [ ] **Step 3: `open_emails_folder`'s cross-platform dispatch, extracted to a mockable function**

```python
# ui/server.py -- add near the top-level helpers (e.g. next to _safe_run_id)
import subprocess  # add to the top-level imports


def open_folder(path: Path) -> None:
    """Cross-platform 'reveal in file manager'. A module-level function (not inlined into the
    route) so tests can monkeypatch it instead of launching a real GUI window -- see
    tests/characterization/test_interface_matrix.py's UI-ROUTE-023 runner, which does exactly
    that, the same way UI-ROUTE-018 already monkeypatches module-level webbrowser.open."""
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 - local-only app, user-triggered
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
```

```python
# ui/server.py -- replace open_emails_folder's body
@app.post("/api/runs/{run_id}/open-emails-folder")
async def open_emails_folder(run_id: str) -> dict[str, Any]:
    run_dir = _safe_run_id(run_id)
    emails_dir = run_dir / "emails"
    if not emails_dir.exists():
        raise HTTPException(404, "Emails have not been generated yet for this run")
    # open_folder does a blocking subprocess.run/os.startfile call -- awaiting it directly in
    # this async route would block the event loop (and every other in-flight request) for
    # however long the OS takes to launch a file-manager window. asyncio.to_thread keeps the
    # route itself non-blocking; the monkeypatch in _route_UI_ROUTE_023 still applies, since
    # asyncio.to_thread resolves `open_folder` as a plain module-global lookup at call time.
    await asyncio.to_thread(open_folder, emails_dir)
    return {"opened": True}
```

`asyncio` is already imported at the top of `ui/server.py` (used elsewhere in the module for the
existing `operations`/queue machinery) — no new import needed.

- [ ] **Step 4: `open_report`'s validation — preserving the existing `webbrowser.open` call**

```python
# ui/server.py -- add a helper near _safe_run_id
def _safe_report_path(run_dir: Path, html_report: str) -> Path | None:
    """None if html_report is not a bare filename resolving inside run_dir -- never lets an
    unvalidated persisted string reach webbrowser.open (UI-ROUTE-030)."""
    candidate = Path(html_report)
    if not html_report or candidate.name != html_report:
        return None  # rejects any path separator, ".."  segment, or absolute path
    resolved = (run_dir / html_report).resolve()
    if resolved.parent != run_dir.resolve():
        return None
    if not resolved.is_file():
        return None
    return resolved
```

```python
# ui/server.py -- replace open_report's body. webbrowser.open is UNCHANGED for a valid
# html_report (UI-ROUTE-018 stays green); the ONLY new behavior is rejecting an invalid one
# before a URL is ever built.
@app.post("/api/runs/{run_id}/open-report")
async def open_report(run_id: str, request: Request) -> dict[str, Any]:
    run_dir = _safe_run_id(run_id)
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise HTTPException(404, "Run not found")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(400, "This run's summary.json is corrupt")
    report_name = summary.get("html_report")
    if not report_name:
        raise HTTPException(404, "This run has no HTML report")
    if _safe_report_path(run_dir, report_name) is None:
        raise HTTPException(400, "This run's recorded report filename is invalid")
    url = f"{request.base_url}runs/{run_id}/{report_name}"
    webbrowser.open(url)
    return {"opened": True, "url": url}
```

`ui/static/app.js` is **not touched** by this task — the archived skeleton's note about it
("ignores the response body") describes a client-side UX nicety (surfacing a 400 error to the
user), not a change any named `UI-ROUTE-*` case requires; scoping it out here rather than
guessing at un-pinned behavior.

- [ ] **Step 5: Update the digest and run**

`generate_emails`'s `scouts.json` read is intentionally left as-is (see Design Note above) —
there is no fifth fix here, only the digest bump for the two case updates from Step 1.

```bash
uv run python tools/check_case_digest.py --update
```

```bash
uv run pytest tests/characterization/test_interface_matrix.py tests/matrix -q
```

- [ ] **Step 6: Commit**

```bash
git add ui/server.py tests/characterization/test_interface_matrix.py tests/matrix/cases/interface_cases.py tests/baselines/preserve_cases.json
git commit -m "fix(ui): cross-platform folder open, validate html_report before use, unlink guard"
```

---

## Task B8.3: Package route surface + parity test

**Goal:** `src/scoutmb/interfaces/web/routes.py` + `composition.py` cover the same route surface
as the now-fixed `ui/server.py`, wired through `JobSupervisor` (no bare `asyncio.create_task`)
and `RunStateMachine` (no `busy` dict), proven equivalent by a parity test driving both apps
through the identical `httpx.AsyncClient` + `ASGITransport` pattern the legacy characterization
suite already uses.

**Files:**
- Create: `src/scoutmb/interfaces/web/routes.py`, `src/scoutmb/interfaces/web/composition.py`
- Modify: `src/scoutmb/interfaces/web/app.py` (registers the new routes)
- Test: `tests/parity/test_local_web_parity.py`

**Acceptance Criteria:**
- [ ] Every route `ui/server.py` exposes has a package-side equivalent with matching status
      codes and response bodies for the same request
- [ ] The package's pdf-extract/schedule-download routes track state via
      `app.state.job_registry` (a `JobSupervisor`) — no bare `asyncio.create_task` with an
      unretained reference
- [ ] `test_local_web_parity.py::test_preserved_routes_match` drives both apps through the same
      request sequence for every `UI-ROUTE-*` `preserve`/`intentional-change` case and asserts
      matching status + body shape
- [ ] `interfaces/web/routes.py` imports `features`/`ports`/`core` only; `composition.py` is the
      only module in `interfaces/web/` that imports an adapter (architecture test)

**Verify:** `uv run pytest tests/parity/test_local_web_parity.py tests/characterization/test_interface_matrix.py tests/architecture -q` → PASS

**Recovery:** Keep `ui/server.py`'s app as the one actually served; leave the package routes
merged but unmounted.

**Steps:**

- [ ] **Step 1: Write the composition root**

```python
# src/scoutmb/interfaces/web/composition.py
"""The ONLY module under interfaces/web permitted to import an adapter (mirrors
interfaces/cli/composition.py's convention; enforced by the same architecture test)."""

from __future__ import annotations

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.html.report import render_report
from scoutmb.features.reporting.service import ReportingService


def build_reporting_service() -> ReportingService:
    return ReportingService(sink=AtomicFileSink(), renderer=render_report)
```

- [ ] **Step 2: Write the parity test (RED first)**

```python
# tests/parity/test_local_web_parity.py
"""D13 parity: the package's create_app(settings) routes must match ui/server.py's (now-fixed)
routes on status code and response body shape, for the same request. Both apps are driven
in-process via httpx.ASGITransport -- the same mechanism tests/characterization/
test_interface_matrix.py already uses for the legacy app -- never a real socket.

_client_for wraps app.router.lifespan_context(app), not just ASGITransport -- ASGITransport
alone does NOT run FastAPI's lifespan, so app.state.settings/job_registry (set inside create_app's
lifespan, Task B8.1) would never be populated and every route touching request.app.state would
raise AttributeError before any assertion ran. An earlier draft of this test file had exactly
that bug."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app


@asynccontextmanager
async def _client_for(data_root: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = UiSettings(data_root=data_root)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.anyio
async def test_health_route_matches(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_scouts_csv_missing_returns_404(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as client:
        response = await client.get("/api/scouts")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_status_route_reports_no_csv(tmp_path: Path) -> None:
    async with _client_for(tmp_path) as client:
        response = await client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "scouts_csv_exists": False,
        "scouts_count": None,
        "scouts_mtime": None,
    }
```

> This is a starting slice of the parity surface, not the complete route-for-route mirror the
> Acceptance Criteria demand. **Before this task is done, extend `routes.py` and this test file
> to cover `/api/pdf-extract`, `/api/schedule-download` (+ pause/resume), `/api/operations/
> {operation_id}/events`, `/api/runs`, and the three `/api/runs/{run_id}/...` routes, reading
> `ui/server.py`'s post-B8.2 bodies for each one's exact behavior** rather than re-deriving it
> from memory — those routes' request/response shapes were already transcribed in Task B8.2's
> steps for the three touched by this sub-plan, and the remaining ones (`list_runs`, `get_scouts`,
> `get_status`, `start_pdf_extract`, `start_schedule_download`, pause/resume, `operation_events`)
> are unchanged from what this plan document quoted in its own "Current-state anchors" reading of
> `ui/server.py` earlier in this session — copy their bodies forward into `routes.py` with
> `busy`/`operations`/`current_download` replaced by `app.state.job_registry` /
   `app.state.run_states` equivalents, not reinvented.

- [ ] **Step 3: Implement the route surface**

```python
# src/scoutmb/interfaces/web/routes.py
"""Package-side route handlers. Imports features/ports/core only -- never an adapter directly
(scoutmb.interfaces.web.composition is the sole adapter-importing module in this package,
enforced by the architecture test). Registered onto the app by create_app()."""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from scoutmb.config import UiSettings

router = APIRouter()


def _read_scouts_rows(settings: UiSettings) -> list[dict[str, str]]:
    with settings.scouts_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@router.get("/api/status")
async def get_status(request: Request) -> dict[str, Any]:
    settings: UiSettings = request.app.state.settings
    if not settings.scouts_csv.exists():
        return {"scouts_csv_exists": False, "scouts_count": None, "scouts_mtime": None}
    rows = _read_scouts_rows(settings)
    mtime = datetime.fromtimestamp(settings.scouts_csv.stat().st_mtime).isoformat(
        timespec="seconds"
    )
    return {"scouts_csv_exists": True, "scouts_count": len(rows), "scouts_mtime": mtime}


@router.get("/api/scouts")
async def get_scouts(request: Request) -> list[dict[str, str]]:
    settings: UiSettings = request.app.state.settings
    if not settings.scouts_csv.exists():
        raise HTTPException(404, "scouts.csv not found")
    rows = _read_scouts_rows(settings)
    return [
        {
            "name": row.get("Attendee Name", "") or "",
            "registrant_type": row.get("Registrant Type", "") or "",
        }
        for row in rows
    ]
```

`request: Request` (FastAPI's request object, giving access to `request.app.state`) is what
every route handler in this module uses to reach the settings the lifespan attached in Task
B8.1 — mirroring how `ui/server.py`'s own `open_report` already takes a `Request` parameter for
`request.base_url`.

- [ ] **Step 4: Wire the router into the factory**

```python
# src/scoutmb/interfaces/web/app.py -- add to create_app, after the health route
    from scoutmb.interfaces.web.routes import router

    app.include_router(router)
```

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/parity/test_local_web_parity.py tests/characterization/test_interface_matrix.py tests/architecture -q
```

```bash
git add src/scoutmb/interfaces/web tests/parity/test_local_web_parity.py
git commit -m "feat(web): package route surface behind create_app, parity-tested against ui/server.py"
```

---

## Task B9.1: `run_app.py`'s port-zero rendezvous + `troop349` desktop entrypoint

**Goal:** Bind the real server socket to port 0 directly and read back the OS-assigned port from
the live socket — removing the probe-bind-close-then-rebind race — and add the `troop349`
desktop console script driving the package app instead of `ui.server.app`.

**Files:**
- Create: `src/scoutmb/interfaces/desktop/__init__.py`, `src/scoutmb/interfaces/desktop/app.py`
- Modify: `run_app.py` (`free_port`/`start_server` merge into one race-free bind)
- Modify: `pyproject.toml` (`troop349` console script)
- Test: `tests/integration/test_rendezvous.py`

**Acceptance Criteria:**
- [ ] The server binds to port 0 exactly once; the actual assigned port is read from that same
      live socket, never from a second, separately-opened probe socket
- [ ] Between the bind and the server accepting connections, no window exists where another
      process could claim the same port — proven by binding many times in a tight loop with no
      failure, not merely asserted
- [ ] A real server started on the bound socket (via `asyncio.start_server(sock=...)`, the same
      parameter shape `uvicorn.Server.serve(sockets=[...])` uses) actually accepts a client
      connection — proving the socket is genuinely handed off and used, not merely bindable
- [ ] `troop349` launches the package app (`scoutmb.interfaces.web.app.create_app`) in a
      pywebview window, mirroring `run_app.py`'s existing `--browser`/native-window split

**Verify:** `uv run pytest tests/integration/test_rendezvous.py -q` → PASS

**Recovery:** Keep `run_app.py`'s existing `free_port()`/`start_server()` split as the launcher
for the legacy app; leave `scoutmb.interfaces.desktop` unreferenced by any console script.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_rendezvous.py
"""B9: binding directly to port 0 and reading the assigned port back from the SAME live socket
removes the race a separate probe-then-close-then-rebind has -- a socket can be reused by
another process the instant it closes, and free_port()/start_server()'s two-step dance in
run_app.py has exactly that gap. This test proves the merged bind never contends with itself
across many rapid iterations, which is the only way a TOCTOU race actually shows up."""

from __future__ import annotations

import socket

from scoutmb.interfaces.web.rendezvous import bind_loopback_socket


def test_bind_loopback_socket_returns_a_working_bound_socket() -> None:
    sock = bind_loopback_socket()
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        sock.close()


def test_many_rapid_binds_never_collide() -> None:
    """Rebinding 50 times in a tight loop is what would expose a probe-close-rebind race in
    practice -- a race window measured in microseconds is far more likely to show up across many
    iterations than one."""
    for _ in range(50):
        sock = bind_loopback_socket()
        try:
            _, port = sock.getsockname()
            assert port > 0
        finally:
            sock.close()


async def test_a_server_actually_accepts_on_the_bound_socket() -> None:
    """The two tests above only prove binding itself never collides -- they don't prove that
    handing the bound socket to a SERVER (rather than a fresh port number) actually works, which
    is the whole point of bind_loopback_socket() existing. asyncio.start_server(sock=...)
    explicitly supports accepting a pre-bound socket (the same parameter shape
    uvicorn.Server.serve(sockets=[...]) uses in run_app.py/interfaces/desktop/app.py) -- this
    test drives a minimal echo server through it and proves a real client connection succeeds,
    without needing a full uvicorn+FastAPI round trip just to prove the socket-handoff
    mechanism."""
    import asyncio

    sock = bind_loopback_socket()
    host, port = sock.getsockname()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(100)
        writer.write(b"echo:" + data)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, sock=sock)
    async with server:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"ping")
        await writer.drain()
        response = await reader.read(100)
        writer.close()
        assert response == b"echo:ping"
```

Run: `uv run pytest tests/integration/test_rendezvous.py -v` → FAIL (module doesn't exist)

- [ ] **Step 2: Implement the race-free bind**

```python
# src/scoutmb/interfaces/web/rendezvous.py
"""Port-zero rendezvous (D30). bind_loopback_socket() binds ONE socket to port 0 and returns it
still open and listening -- the caller reads the assigned port off THIS socket
(sock.getsockname()) and hands the SAME socket to uvicorn, rather than run_app.py's prior
two-step dance: probe-bind a throwaway socket to discover a free port, close it, then bind a
SECOND, separate socket to that port number later. Between that close and the later bind, the
OS is free to hand the same port to a different process -- this removes the gap by never
closing the socket that discovered the port."""

from __future__ import annotations

import socket


def bind_loopback_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    return sock
```

- [ ] **Step 3: Re-point `run_app.py` at the race-free bind**

```python
# run_app.py -- replace free_port()/start_server() with one function
from scoutmb.interfaces.web.rendezvous import bind_loopback_socket


def start_server_on_free_port() -> tuple[threading.Thread, int]:
    sock = bind_loopback_socket()
    port = sock.getsockname()[1]
    config = uvicorn.Config(app=server.app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # uvicorn.Server.serve(sockets=[...]) binds no NEW socket of its own -- it accepts
        # connections on the one already bound above, closing the exact gap this task exists
        # to remove.
        loop.run_until_complete(uvicorn_server.serve(sockets=[sock]))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, port


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser", action="store_true",
        help="Open in the system's default browser instead of a native window.",
    )
    args = parser.parse_args()

    _thread, port = start_server_on_free_port()
    base_url = f"http://127.0.0.1:{port}/"
    wait_until_ready(base_url + "api/health")
    ...  # unchanged below this point
```

`free_port()` and the old `start_server(port)` are deleted; `wait_until_ready` is unchanged.

- [ ] **Step 4: Add the `troop349` desktop entrypoint**

```python
# src/scoutmb/interfaces/desktop/__init__.py
```

```python
# src/scoutmb/interfaces/desktop/app.py
"""troop349 console script: native pywebview window around the package's create_app(settings),
using the same race-free port-zero bind as run_app.py."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
import urllib.error
import urllib.request

import uvicorn
import webview

from scoutmb.config import UiSettings
from scoutmb.interfaces.web.app import create_app
from scoutmb.interfaces.web.rendezvous import bind_loopback_socket


def _wait_until_ready(url: str, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready at {url}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch the Troop 349 Summer Camp Command Program UI."
    )
    parser.add_argument(
        "--browser", action="store_true",
        help="Open in the system's default browser instead of a native window.",
    )
    args = parser.parse_args()

    app = create_app(UiSettings.resolve())
    sock = bind_loopback_socket()
    port = sock.getsockname()[1]
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = uvicorn.Server(config)

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(uvicorn_server.serve(sockets=[sock]))

    threading.Thread(target=run, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}/"
    _wait_until_ready(base_url + "api/health")

    if args.browser:
        import webbrowser

        webbrowser.open(base_url)
        print(f"Serving at {base_url} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    else:
        webview.create_window(
            "Troop 349 Summer Camp Command Program", base_url,
            width=1150, height=820, min_size=(760, 560),
        )
        webview.start()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```toml
# pyproject.toml -- [project.scripts], add
troop349 = "scoutmb.interfaces.desktop.app:main"
```

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/integration/test_rendezvous.py -q
```

```bash
git add src/scoutmb/interfaces/web/rendezvous.py src/scoutmb/interfaces/desktop run_app.py pyproject.toml tests/integration/test_rendezvous.py
git commit -m "feat(runtime): race-free port-zero bind; add troop349 desktop entrypoint"
```

---

## Task B9.2: `troop349-schedule` entrypoint + three-script entrypoint parity

**Goal:** `troop349-schedule` wraps `async_main`/`ScheduleConfig` exactly as `troop349-pdf`
already wraps stage 1, and one parity test proves all three console scripts (`troop349-pdf`,
`troop349-schedule`, `troop349`) match the flat scripts they replace on `--help`, exit codes,
stdout, and stderr — run as installed subprocesses from outside the repository.

**Files:**
- Create: `src/scoutmb/interfaces/cli/schedule.py`
- Modify: `pyproject.toml` (`troop349-schedule` console script)
- Test: `tests/parity/test_entrypoint_parity.py`

**Acceptance Criteria:**
- [ ] `troop349-schedule --help` matches `python scout_schedule_cli.py --help` except for the
      program name — run as installed subprocesses, stdout compared byte for byte (program name
      aside)
- [ ] A missing required `--input` argument exits `2` with matching stderr on both, run as
      subprocesses
- [ ] A handled runtime exception (a nonexistent `--input` **file**, as opposed to a missing
      argument — this reaches `main()`'s `except Exception` branch rather than argparse's own
      error path) exits `2` with a matching `"ERROR: ..."` stderr prefix on both, run as
      subprocesses
- [ ] `KeyboardInterrupt` → exit `130` is proven by a **unit test** against each `main()`
      in-process (monkeypatching `asyncio.run` to raise `KeyboardInterrupt`), not a subprocess —
      reliably delivering a real `SIGINT` to a subprocess mid-run would require the process to
      actually be blocked on something (e.g. a live Playwright launch), which is out of scope for
      an entrypoint-parity check; this narrower unit test still proves the exception-to-exit-code
      mapping itself, which is the only thing per-script and not already covered by subprocess
      behavior
- [ ] The subprocess-based checks above are run as **installed console-script subprocesses**,
      from a working directory outside the repository, not via `main()` called in-process — the
      `KeyboardInterrupt` check is the one deliberate, stated exception to that rule
- [ ] `troop349`/`troop349-pdf`/`troop349-schedule` all pass the applicable subset of the above
      (a full "success" acquisition run via subprocess is out of scope here — that path is
      already proven by `tests/parity/test_acquisition_parity.py` and the characterization suite;
      this task's job is argv/exit-code/stderr parity, not re-proving the acquisition pipeline)

**Verify:** `uv run pytest tests/parity/test_entrypoint_parity.py -q` → PASS

**Recovery:** Remove the new console script from `pyproject.toml`; `scout_schedule_cli.py`
remains the only way to run stage 2.

**Steps:**

- [ ] **Step 1: Write the failing parity test**

```python
# tests/parity/test_entrypoint_parity.py
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


def _strip_prog_name(text: str, prog: str) -> str:
    return re.sub(rf"\b{re.escape(prog)}\b", "PROG", text)


def test_schedule_help_matches_flat_script(tmp_path: Path) -> None:
    flat = _run([sys.executable, str(REPO_ROOT / "scout_schedule_cli.py"), "--help"], cwd=tmp_path)
    packaged = _run(["troop349-schedule", "--help"], cwd=tmp_path)

    assert flat.returncode == packaged.returncode == 0
    assert _strip_prog_name(flat.stdout, "scout_schedule_cli.py") == _strip_prog_name(
        packaged.stdout, "troop349-schedule"
    )


def test_schedule_missing_required_input_matches_exit_code_and_stderr(tmp_path: Path) -> None:
    flat = _run([sys.executable, str(REPO_ROOT / "scout_schedule_cli.py")], cwd=tmp_path)
    packaged = _run(["troop349-schedule"], cwd=tmp_path)
    assert flat.returncode == packaged.returncode == 2
    assert _strip_prog_name(flat.stderr, "scout_schedule_cli.py") == _strip_prog_name(
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
    assert _strip_prog_name(flat.stdout, "pdf_to_scouts.py") == _strip_prog_name(
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
```

Run: `uv run pytest tests/parity/test_entrypoint_parity.py -v` → FAIL (`troop349-schedule` not
installed, `scoutmb.interfaces.cli.schedule` doesn't exist)

- [ ] **Step 2: Implement `interfaces/cli/schedule.py`**

```python
# src/scoutmb/interfaces/cli/schedule.py
"""troop349-schedule console script: argument-for-argument identical to scout_schedule_cli.py's
CLI. Interface layer -- argument parsing and orchestration only, mirroring interfaces/cli/pdf.py's
existing shape. Playwright/acquisition/reporting all live in scout_schedule_cli.py itself at this
point in the plan (retirement is sub-plan 4's Task B10), so this module delegates straight to
scout_schedule_cli.async_main -- there is no package-side async_main to call yet."""

from __future__ import annotations

import asyncio
import sys

import scout_schedule_cli as legacy


def main() -> int:
    config = legacy.parse_args()
    try:
        return asyncio.run(legacy.async_main(config))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

> This delegates to the still-legacy `scout_schedule_cli` module rather than a package-side
> `async_main` — there isn't one yet at this point in the plan sequence (acquisition still lives
> in `scout_schedule_cli.py`; sub-plan 1 built `AcquisitionService` as an additive parity-tested
> unit, not yet the thing `async_main` calls). This console script is therefore a genuine
> **Form-2 adapting shim** in the Phase B spec's sense (parse → delegate → return), which is
> exactly the permitted shape for a module that must exist before its full package-side
> equivalent does.

```toml
# pyproject.toml -- [project.scripts], add
troop349-schedule = "scoutmb.interfaces.cli.schedule:main"
```

- [ ] **Step 3: Install the package in editable mode so the new console scripts exist, then run**

```bash
uv pip install -e .
uv run pytest tests/parity/test_entrypoint_parity.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/scoutmb/interfaces/cli/schedule.py pyproject.toml tests/parity/test_entrypoint_parity.py
git commit -m "feat(cli): add troop349-schedule entrypoint, prove three-script parity"
```

---

## Sub-plan gate (feeds Gate 2)

- `UI-ROUTE-023`/`UI-ROUTE-030` landed with updated expectations and a bumped digest;
  `UI-ROUTE-024..029` **and** `UI-ROUTE-021` all pass unmodified — no undeclared seventh
  intentional-change row.
- Importing `scoutmb.interfaces.web.app` performs no I/O; `create_app(settings)` builds a fresh
  app + `JobSupervisor` per call; `settings.ensure_dirs()` runs before any `StaticFiles` mount
  could check for the directory's existence.
- The package route surface matches `ui/server.py`'s (post-fix) behavior for every route,
  proven by a parity test that actually runs the app's lifespan (not bare `ASGITransport`).
- `open_folder`'s blocking OS call is wrapped in `asyncio.to_thread`, never blocking the route's
  event loop.
- The port-zero bind never leaves a probe-then-rebind gap, and a real server started on the
  bound socket actually accepts a connection — not merely proven bindable; `troop349` launches
  the package app.
- `troop349-pdf`/`troop349-schedule`/`troop349` all match their flat-script predecessors on
  `--help`, missing-argument exit code, and a handled-exception exit code + stderr prefix, run as
  installed subprocesses outside the repo; `KeyboardInterrupt` → 130 is proven by a unit test
  against each `main()` — no acceptance criterion here claims subprocess coverage it doesn't have.
- `UiSettings` lives in `scoutmb.config`, imported consistently everywhere in this sub-plan —
  no `scoutmb.ui_settings` module was created.
- `uv run pytest -q` green with no regressions.

**NO-GO:** Keep `ui/server.py`'s app as the one actually served; restore `run_app.py`'s original
`free_port`/`start_server` split; remove the new console scripts from `pyproject.toml`; return
the specific failing behavior to its task.
