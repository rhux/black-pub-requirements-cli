# Slice 2b.1 — ScoutingEvent Gateway & Bounded Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Revision note (post-Codex review):** This plan was rewritten after an independent review
> (`/codex`) found several critical defects in the first draft: the gateway's DTO discarded the
> upstream envelope/status/name-discovery/HTML-cleaning behavior `process_scout` currently
> preserves; the checkpoint store was built but never actually composed into anything; the
> circuit breaker got rebuilt fresh per scout (defeating its own cross-scout premise) and
> conflated retry-attempt failures with logical failures; the egress check as designed would have
> raised on every existing synthetic test case (all of which use `scoutingevent.com`, which is
> not loopback and carries no opt-in by default); `AcquisitionService` called `Path.write_text()`
> directly instead of routing through the `ArtifactSink` port; `CorruptCheckpoint` didn't subclass
> `ScoutmbError`; a "frozen" checkpoint held a plain mutable dict; and one test had a real bug (a
> shared stub whose `locator()` unconditionally raises, breaking the one test that needed it not
> to). All of these are fixed below. The task numbering changed: B5.4 is now one-scout
> composition only (no checkpoint, no breaker-state ownership); a new Task B5.5 owns run-scoped
> batch orchestration, which is where the checkpoint and the shared breaker actually get used.

**Goal:** Extract a ScoutingEvent gateway that owns the attendee session, requirement schema
validation, and egress-policy enforcement; freeze `ScoutResult`; and add a bounded, run-scoped
acquisition batch (retry + circuit breaker + resumable checkpoints) in front of it — landing
`NET-WIRE-001/002`, `ACQ-REQ-004`, `ACQ-HASREQ-002`, `ACQ-BREAKER-001/002/003`, and
`ACQ-RESUME-001/002/003/004`.

**Architecture:** Two new ports (`ports/scoutevent.py`, `ports/checkpoint_store.py`) plus one
adapter package (`adapters/scoutevent/`) wrap the Playwright-mediated schedule/requirement calls
that today live inline in `scout_schedule_cli.process_scout`. `features/acquisition/service.py`
handles ONE scout (gateway session + schema validation + per-request retry, routed through the
existing `ArtifactSink` port for raw-file writes — never `Path.write_text()` directly).
`features/acquisition/batch.py` handles a WHOLE RUN: it owns the single shared `RetryPolicy`
(so the breaker sees failures across scouts, not just within one), the checkpoint store, and
`RunIdentity` hydration/persistence. `scout_schedule_cli.py` keeps `process_scout`'s signature and
callers unchanged — its body becomes a thin driver over the new feature — so `async_main`, the
UI, and every characterization/parity test that calls `process_scout` directly need no changes
in this sub-plan.

**Tech Stack:** Python 3.12, Playwright (`playwright.async_api`, imported only under
`TYPE_CHECKING` — never at runtime module scope, since it is an optional dependency), pytest +
the existing strict-fake harness (`tests/fakes/acquisition.py`, `tests/fakes/browser.py`,
`tests/fakes/clock.py`), the `Runner[InputT, ObservationT]` matrix-parity protocol already in
`tests/matrix/model.py`.

**Global Constraints:**
- No new third-party dependency. Schema validation is hand-written (matching
  `core/output_schemas.py`'s existing `_text`/`_flag` style), not a JSON-Schema library.
- The retry backoff stays `500 * attempt` ms for attempts 1-3 (characterized, unchanged) —
  including the wait after the third and final attempt, which the legacy loop also performs
  unconditionally; the circuit breaker and checkpoint are additive, not replacements for it.
- `process_scout`'s public signature (`browser, scout, args, raw_dir, run_identity`) does not
  change — every existing caller (`async_main`, `tests/characterization/test_acquisition_matrix.py`,
  `tests/characterization/test_browser_matrix.py`) keeps working unmodified.
- Every write this sub-plan introduces (the checkpoint file, the raw/ session dumps) goes
  through an atomic write path, matching D11's "a failed write never truncates the previous
  file" contract — `AcquisitionService` routes raw/ writes through the existing `ArtifactSink`
  port (`self.sink.publish_text(...)`), never `Path.write_text()` directly, mirroring exactly how
  `ReportingService` (2a, already merged) routes every content write through its own injected
  sink while still calling `.mkdir(parents=True, exist_ok=True)` itself for the output directory
  (directory creation is orchestration, not "producing an external format" — the thing the
  dependency rule actually forbids a feature from doing is writing *content*).
- `features/acquisition/` imports `ports` and `core` only — never `playwright.async_api`
  directly, not even under `TYPE_CHECKING` in the feature layer (only the adapter needs the real
  types) — enforced by `tests/architecture/test_dependency_rules.py`.
- Every exception this sub-plan defines subclasses `ScoutmbError` — `errors.py`'s own docstring
  says it is "the base class for every error this package raises," and there is no reason for a
  narrower exception to opt out of that.

**User decisions (already made):** Split slice 2b into four independent sub-plans by subsystem;
this sub-plan covers B4 (gateway) + B5 (acquisition) only.

**Design decisions this sub-plan makes** (the Phase B spec fixes contracts, not these — flagged
here for review before execution, per the spec's own contracts-vs-mechanisms distinction):

1. **Gateway port shape.** `ScoutingEventGateway.open_session()` returns an async context
   manager yielding a `ScoutingEventSession` — neither type's Protocol method signatures mention
   `playwright.async_api.Page`/`Browser`. The adapter (`adapters/scoutevent/playwright_gateway.py`)
   holds the real `Browser` and constructs a `BrowserContext`/`Page` per session; the acquisition
   feature never imports Playwright, and the adapter itself only imports it under
   `TYPE_CHECKING` (see Design Decision 5).
2. **Requirement schema-drift required fields.** `MDM_LKP_BADGE_REQ_ID` (→ `requirement_id`) and
   at least one of `REQ_NBR_WEB_DISPLAY`/`REQ_NBR` (→ `requirement_number`) are required; every
   other field keeps today's `_text`/`_flag` coercion (missing → blank/false is fine for those —
   they were never identity-bearing). `ACQ-REQ-004`'s fixture (`{"MERIT_BADGE_NAME": "Chess"}`,
   nothing else) is missing both required fields under this rule, so it is rejected — matching
   the case's `target_observation`. **This required-field set is a judgment call, not something
   the spec pins — confirm it before executing Task B4.2.**
3. **Checkpoint store is a new narrow port**, not a reuse of `ArtifactSink` and not the
   `ports/storage.py` the spec explicitly declines to create. Justification: it has a real second
   implementation for tests (a fake checkpoint store, same shape as every other port in this
   codebase) and a single, fixed JSON schema — the spec's objection was to a *generic* storage
   abstraction with nothing behind it, which this is not. It is composed at the **batch** level
   (Task B5.5), not inside the one-scout `AcquisitionService` — a single scout's acquisition has
   no business deciding whether the run as a whole should skip it or persist state.
4. **Checkpoint identity before `attendee_id` exists.** A scout is keyed by `scout.url` (the QR
   link) for "already completed" tracking, since `attendee_id` is only known after a successful
   schedule fetch — `scout.url` is the one stable value present in the input file.
5. **Playwright types are imported only under `TYPE_CHECKING` in the adapter module.** Every use
   of `Browser`/`BrowserContext`/`Page`/`Response` in `playwright_gateway.py` is duck-typed —
   nothing does `isinstance()` against them or constructs one directly (the `Browser` is always
   handed in from outside, from `async_main`'s own `playwright.chromium.launch(...)` call). A
   module-scope `from playwright.async_api import ...` would therefore be a real, avoidable
   `ImportError` risk for a distribution the `acquisition` extra makes optional, with no runtime
   benefit — `from __future__ import annotations` already defers every annotation to a string, so
   `TYPE_CHECKING`-only imports give mypy the real types with zero runtime cost, matching the
   precedent already in this codebase (`tools/check_case_digest.py`'s own `if TYPE_CHECKING:`
   import).
6. **The circuit breaker and per-scout success/failure recording live at the batch level
   (`features/acquisition/batch.py`), not inside `AcquisitionService.process()`.** A per-scout
   service has no way to see "how many *scouts* failed in a row" — only the batch loop, which
   sees every scout, can. `RetryPolicy` still lives inside `AcquisitionService` for its **wait**
   mechanism (per-request backoff), constructed once by the batch and shared across every scout
   it processes, so its breaker state is genuinely cumulative across the run.

---

## Current-state anchors (verified against the branch, not the spec's prose)

- `scout_schedule_cli.navigate_and_trigger_schedule` (lines 248-294) and `.post_requirement`
  (lines 297-329) are the two call sites `NET-WIRE-002`/`NET-WIRE-001` target. Neither calls
  `scoutmb.network_policy.assert_egress_allowed` today — confirmed by reading both functions.
- `scout_schedule_cli.discover_name` (lines 227-245) is called once per scout, right after the
  attendee ID is known (`process_scout` line 368: `result.name = await discover_name(page,
  scout.name)`), and its return value **replaces** the scout's own input name whenever the DOM
  offers a better one. Any gateway redesign that drops this call silently reverts every scout to
  its input-file name, which several `ACQ-*` cases' `expected_legacy` values do not expect.
- `process_scout` writes the **complete** schedule envelope (`schedule_payload`, i.e. the whole
  `{status, data}` object) to `{slug}-schedule.json` (line 374), and the **complete** requirement
  envelope to `{slug}-{class}-requirements.json` (line 437) — not the extracted `data` array
  alone. It also checks `schedule_payload["status"]["status"] != 1` (line 378) and
  `requirement_payload["status"]["status"] != 1` (line 441) as its own failure conditions,
  independent of what is inside `data`. A gateway that returns only the `data` rows loses both
  the raw audit trail and the failure-status check in one move.
- `RequirementRecord.description` is built via `clean_html_description(str(req.get("REQ_DESCR")
  or ""))` (line 459) — never the raw `REQ_DESCR` string. `clean_html_description` (lines
  208-214) strips `<br>` tags to newlines, strips remaining tags, unescapes HTML entities, and
  collapses blank-line runs.
- The retry loop is in `process_scout` (lines 421-429): `for attempt in range(1, 4): ... await
  page.wait_for_timeout(500 * attempt)`, unconditionally on every failed attempt including the
  third. No breaker, no checkpoint anywhere in this file.
- `scoutmb.core.models.ScoutResult` (models.py:72-79) is **already** the frozen, tuple-based
  target shape from Task 14. The legacy `scout_schedule_cli.ScoutResult` (lines 83-90) is a
  separate, still-mutable, list-based class that `process_scout` actually constructs and
  `.append`s onto. B5's freeze is: make `process_scout` build the package `ScoutResult`
  directly and turn the legacy class into a re-export — not a new frozen shape.
- `RunIdentity` (`core/identity.py:34-51`) exposes only `output_id()`; it has no way to seed
  itself from a prior run's map or export its current map. Batch-level checkpoint hydration (Task
  B5.5) needs both, added as two small public methods — a legitimate, narrow touch to existing
  2a code, not a new file.
- **The egress policy will reject every existing synthetic test fixture unless the test suite
  opts in.** `assert_egress_allowed` (`network_policy.py:19-25`) only permits `127.0.0.1`/`::1`/
  `localhost`, or any host at all when `SCOUTMB_ALLOW_LIVE_SERVICE` is set.
  `tests/matrix/cases/acquisition_cases.py` uses `URL_A = "https://scoutingevent.com/mobile/
  checkin?t=TESTTOKEN_A"` throughout (line 59) — not loopback. Once `navigate_and_trigger_
  schedule`/`post_requirement` route through the gateway (which calls `assert_egress_allowed`),
  every existing `ACQ-*` `process`/`raw` test would raise `ExternalNetworkBlocked` immediately
  unless the opt-in is set for those tests. Since the fakes never open a real socket, this is
  safe to do (pytest-socket's own host-restriction mode, `tests/conftest.py`, still blocks any
  *actual* non-loopback connection regardless) — Task B4.1 adds the opt-in as a scoped test
  fixture, not a change to `assert_egress_allowed` itself.
- `tests/matrix/cases/acquisition_cases.py`'s `evidence_reference` line numbers (e.g. "async_main
  lines 1799-1873", "post_requirement lines 454-486") are **stale** — the current file is 918
  lines total, `async_main` starts at line 827, `post_requirement` at line 297. These are
  pre-refactor references left over from before Slice 1a/2a shrank the file. Not blocking, but
  worth a follow-up cleanup pass over the matrix case docstrings — filed as a note, not a task,
  since it touches no behavior.
- The digest-refresh command is `uv run python tools/check_case_digest.py --update`
  (`tools/check_case_digest.py:6-9`), and it writes `tests/baselines/preserve_cases.json`
  (`tools/check_case_digest.py:25`) — not `phase_a.json`, which is a different, coverage-baseline
  file. Every step below that regenerates the digest uses this exact command.

---

## Task B4.1: `ports/scoutevent.py` + Playwright navigation gateway (schedule fetch)

**Goal:** Extract `navigate_and_trigger_schedule` behind a gateway that calls
`assert_egress_allowed` before navigating, landing `NET-WIRE-002`, preserving DOM name discovery
and the full schedule envelope, with zero observable behavior change to the schedule-fetch path.

**Files:**
- Create: `src/scoutmb/ports/scoutevent.py`, `src/scoutmb/adapters/scoutevent/__init__.py`,
  `src/scoutmb/adapters/scoutevent/playwright_gateway.py`, `tests/characterization/conftest.py`
- Modify: `scout_schedule_cli.py` (`navigate_and_trigger_schedule` becomes a thin wrapper)
- Test: `tests/unit/scoutevent/test_playwright_gateway.py`,
  `tests/parity/test_scoutevent_adapter_parity.py`

**Acceptance Criteria:**
- [ ] `PlaywrightScoutingEventGateway.open_session().fetch_schedule(qr_url, timeout, fallback_name)`
      calls `assert_egress_allowed(urlparse(qr_url).hostname)` before `page.goto`
- [ ] A blocked host raises `ExternalNetworkBlocked` and never calls `page.goto`
- [ ] `ScheduleFetchResult` carries the **full** schedule envelope (`payload`), the resolved
      `attendee_id`, and the DOM-discovered (or fallback) `display_name` — not a stripped `rows`
      tuple
- [ ] `features/`, `ports/`, `core/` still import zero Playwright symbols, even under
      `TYPE_CHECKING` (architecture test) — only the adapter may
- [ ] Every `ACQ-*` `process`/`raw`/`asset` context in `tests/characterization/test_acquisition_matrix.py`
      still passes unmodified — this task changes internal wiring, not the observed behavior

**Verify:** `uv run pytest tests/unit/scoutevent tests/parity/test_scoutevent_adapter_parity.py tests/characterization/test_acquisition_matrix.py tests/architecture -q` → PASS

**Recovery:** Keep `navigate_and_trigger_schedule`'s current body as the live path; leave the
gateway adapter unreferenced until the egress check is proven equivalent.

**Steps:**

- [ ] **Step 1: Scope the egress opt-in to the tests that need it**

Every acquisition characterization/parity/unit test drives fakes against `scoutingevent.com`
URLs, never a real socket. Once the gateway wires in `assert_egress_allowed`, these tests need
the opt-in — narrowly, so `tests/network/test_offline_policy.py`'s own default-denied assertions
elsewhere in the suite are untouched.

```python
# tests/characterization/conftest.py
"""Acquisition/interface characterization tests drive strict FAKES against synthetic
scoutingevent.com URLs -- never a real socket (tests/conftest.py's pytest-socket
host-restriction mode still blocks any actual non-loopback connection regardless). Once the
gateway wires assert_egress_allowed into the schedule/requirement fetch path, these fake-driven
tests need the policy opt-in or every one of them raises ExternalNetworkBlocked immediately."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _allow_synthetic_scoutingevent_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
```

The same fixture is needed under `tests/parity/`, `tests/integration/`, `tests/unit/scoutevent/`,
and `tests/unit/acquisition/` — add an identical `conftest.py` to each of those four directories
in this step (five files total, all four-line copies of the one above). `tests/network/` and
`tests/unit/` (top level, outside `acquisition/`) are deliberately excluded, so
`NET-POLICY-002`'s own `monkeypatch.delenv(...)` proving denial-without-opt-in keeps working
unaffected.

- [ ] **Step 2: Write the failing unit test for the egress check**

```python
# tests/unit/scoutevent/test_playwright_gateway.py
"""NET-WIRE-002: the Playwright navigation gateway must consult assert_egress_allowed before
any navigation, and never navigate at all when the host is blocked. Two distinct stub pages are
used deliberately: the blocked-host test's stub must never reach a selector lookup at all (so it
raises AssertionError if one occurs), while the allowed-host test's stub DOES reach that code
path (egress passes, then the real navigate_and_trigger_schedule body runs its full selector/
click fallback against a page with no real response ever arriving) -- sharing one "selector
lookups always fail" stub between both tests would make the allowed-host test fail on the wrong
exception. This was a real bug in an earlier draft of this test file."""

from __future__ import annotations

import pytest

from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.errors import ExternalNetworkBlocked


class _NeverNavigatesPage:
    """For the blocked-host test only: any call past the egress check is a test failure."""

    def __init__(self) -> None:
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **kwargs: object) -> None:
        self.goto_calls.append(url)

    def locator(self, selector: str) -> object:
        raise AssertionError("blocked navigation must return before any selector lookup")


class _AllowedHostStubPage:
    """For the allowed-host test: navigation proceeds, no response ever arrives, so the real
    navigate_and_trigger_schedule body runs its full selector-fallback path and eventually times
    out -- this stub must tolerate every call that path makes, not reject them."""

    def __init__(self) -> None:
        self.goto_calls: list[str] = []
        self._response_listeners: list[object] = []

    async def goto(self, url: str, **kwargs: object) -> None:
        self.goto_calls.append(url)

    def on(self, event: str, callback: object) -> None:
        if event == "response":
            self._response_listeners.append(callback)

    def remove_listener(self, event: str, callback: object) -> None:
        pass

    async def wait_for_timeout(self, milliseconds: int) -> None:
        pass

    def locator(self, selector: str) -> "_EmptyLocator":
        return _EmptyLocator()

    async def evaluate(self, script: str) -> None:
        pass


class _EmptyLocator:
    async def count(self) -> int:
        return 0


@pytest.mark.matrix_case(case_id="NET-WIRE-002", context_id="net-wire", lane="default")
async def test_blocked_host_raises_and_never_navigates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    page = _NeverNavigatesPage()

    with pytest.raises(ExternalNetworkBlocked) as exc_info:
        await PlaywrightScoutingEventGateway._fetch_schedule_on_page(
            page, "https://evil.example.com/mobile/checkin?t=X", timeout_seconds=5
        )

    assert exc_info.value.host == "evil.example.com"
    assert page.goto_calls == []


async def test_loopback_host_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    page = _AllowedHostStubPage()

    # navigate_and_trigger_schedule's own response-future machinery will time out against this
    # stub page (no response event ever fires) -- that's fine, this test only proves the egress
    # check ran and goto() was reached, not that the full schedule flow completes.
    with pytest.raises(TimeoutError):
        await PlaywrightScoutingEventGateway._fetch_schedule_on_page(
            page, "https://127.0.0.1/mobile/checkin?t=X", timeout_seconds=0
        )
    assert page.goto_calls == ["https://127.0.0.1/mobile/checkin?t=X"]
```

Run: `uv run pytest tests/unit/scoutevent/test_playwright_gateway.py -v` → FAIL (module doesn't exist)

- [ ] **Step 3: Define the port**

```python
# src/scoutmb/ports/scoutevent.py
"""The seam the ScoutingEvent session adapter implements (D22).

Neither Protocol below names a Playwright type. The acquisition feature drives a session
through these two methods only; the concrete Browser/Context/Page lifecycle is the adapter's
business, kept out of features/ and core/ so the dependency-rule architecture test can prove it.

ScheduleFetchResult/fetch_requirements return the FULL upstream envelope (status + data), not
just the data rows -- process_scout today writes the complete envelope to raw/ and checks its
own status field independently of what's inside data (scout_schedule_cli.py:374,378,437,441).
A gateway that stripped the envelope down to `rows` would silently drop both behaviors.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ScheduleFetchResult:
    attendee_id: str
    display_name: str
    payload: Mapping[str, Any]


class ScoutingEventSession(Protocol):
    async def fetch_schedule(
        self, qr_url: str, timeout_seconds: int, fallback_name: str
    ) -> ScheduleFetchResult: ...

    async def fetch_requirements(
        self, attendee_id: str, class_p4_id: str
    ) -> Mapping[str, Any]: ...


class ScoutingEventGateway(Protocol):
    def open_session(self) -> AbstractAsyncContextManager[ScoutingEventSession]: ...
```

- [ ] **Step 4: Write the adapter, egress-checked, Playwright imported only under `TYPE_CHECKING`**

```python
# src/scoutmb/adapters/scoutevent/__init__.py
```

```python
# src/scoutmb/adapters/scoutevent/playwright_gateway.py
"""Playwright-backed ScoutingEventGateway. Owns the Browser/Context/Page lifecycle so
features/acquisition never imports playwright.async_api (NET-WIRE-002).

Playwright's types are imported only under TYPE_CHECKING: every use in this module is duck-typed
(nothing does isinstance() against Browser/Page/Response, and Browser is always handed in from
outside -- async_main's own playwright.chromium.launch() call). `from __future__ import
annotations` defers every annotation to a string, so a TYPE_CHECKING-only import gives mypy the
real types with zero runtime import cost -- important because playwright is the `acquisition`
optional extra, and a bare module-scope import here would be an avoidable ImportError risk for
a build without it installed.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from scoutmb.network_policy import assert_egress_allowed
from scoutmb.ports.scoutevent import ScheduleFetchResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Response

DEAD_ASSET_HOSTS = {
    "mike.dev.admin.247scouting.com",
    "mike.dev.scoutingevent.com",
}


def form_values(post_data: str | None) -> dict[str, str]:
    from urllib.parse import parse_qs

    parsed = parse_qs(post_data or "", keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def is_schedule_response(response: "Response") -> bool:
    if "ajax_mobile.php" not in response.url:
        return False
    return form_values(response.request.post_data).get("getUnitClass", "").lower() == "true"


async def discover_name(page: "Page", fallback: str) -> str:
    """Exact mirror of scout_schedule_cli.discover_name (lines 227-245) -- moved here because
    the gateway is now what calls it, right after the attendee ID is known, matching
    process_scout's existing ordering."""
    if fallback:
        return fallback
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count():
                text = (await locator.first.inner_text()).strip()
                if text and text.lower() not in {"schedule", "event", "menu"}:
                    return text
        except Exception:
            pass
    return "Unknown Scout"


class _PlaywrightSession:
    def __init__(self, context: "BrowserContext", page: "Page") -> None:
        self._context = context
        self._page = page

    async def fetch_schedule(
        self, qr_url: str, timeout_seconds: int, fallback_name: str
    ) -> ScheduleFetchResult:
        response = await PlaywrightScoutingEventGateway._fetch_schedule_on_page(
            self._page, qr_url, timeout_seconds
        )
        values = form_values(response.request.post_data)
        attendee_id = values.get("attendeeID", "")
        payload = await response.json()
        display_name = await discover_name(self._page, fallback_name)
        return ScheduleFetchResult(attendee_id=attendee_id, display_name=display_name, payload=payload)

    async def fetch_requirements(self, attendee_id: str, class_p4_id: str) -> dict[str, Any]:
        from scoutmb.adapters.scoutevent.http_gateway import fetch_requirement_payload

        return await fetch_requirement_payload(self._page, attendee_id, class_p4_id)


class PlaywrightScoutingEventGateway:
    """ScoutingEventGateway over one already-launched Browser. One instance per run."""

    def __init__(self, browser: "Browser", *, allow_dead_assets: bool = False) -> None:
        self._browser = browser
        self._allow_dead_assets = allow_dead_assets

    @staticmethod
    async def _fetch_schedule_on_page(page: Any, qr_url: str, timeout_seconds: int) -> "Response":
        """The exact navigate_and_trigger_schedule body, with one addition: the egress check
        below runs before page.goto and nowhere else navigates. A staticmethod (not a bare
        module function) so the unit test can call it directly against a stub page with no real
        BrowserContext, while still reading naturally as "the gateway's schedule-fetch primitive"
        at the call site inside _PlaywrightSession.fetch_schedule above."""
        from urllib.parse import urlparse

        host = urlparse(qr_url).hostname or ""
        assert_egress_allowed(host)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        async def inspect_response(response: Any) -> None:
            if not future.done() and is_schedule_response(response):
                future.set_result(response)

        def on_response(response: Any) -> None:
            asyncio.create_task(inspect_response(response))

        page.on("response", on_response)
        try:
            await page.goto(qr_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            await page.wait_for_timeout(1200)
            if not future.done():
                selectors = [
                    'a[href="#scoutPage"]',
                    'a[href$="event.html#scoutPage"]',
                    'a:has-text("Schedule")',
                ]
                clicked = False
                for selector in selectors:
                    locator = page.locator(selector)
                    try:
                        if await locator.count():
                            await locator.first.click(force=True, timeout=5000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    await page.evaluate(
                        """() => {
                            const link = document.querySelector('a[href="#scoutPage"]') ||
                                         [...document.querySelectorAll('a')].find(a =>
                                             (a.textContent || '').trim().toLowerCase() === 'schedule');
                            if (link) link.click();
                        }"""
                    )
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            page.remove_listener("response", on_response)

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[_PlaywrightSession]:
        context = await self._browser.new_context(ignore_https_errors=True)
        if not self._allow_dead_assets:

            async def block_dead_assets(route: Any) -> None:
                try:
                    hostname = (
                        re.sub(r"^https?://", "", route.request.url).split("/", 1)[0].split(":", 1)[0]
                    )
                    if hostname in DEAD_ASSET_HOSTS:
                        await route.abort()
                    else:
                        await route.continue_()
                except Exception:
                    await route.continue_()

            await context.route("**/*", block_dead_assets)
        page = await context.new_page()
        try:
            yield _PlaywrightSession(context, page)
        finally:
            await context.close()
```

- [ ] **Step 5: Point `scout_schedule_cli.navigate_and_trigger_schedule` at the gateway**

The characterization suite calls `scout_schedule_cli.navigate_and_trigger_schedule` directly
(`tests/characterization/test_acquisition_matrix.py`'s `form`/`process` contexts), so this
function keeps its exact signature — its body becomes a call through the gateway's staticmethod:

```python
# scout_schedule_cli.py -- replace navigate_and_trigger_schedule's body
async def navigate_and_trigger_schedule(page: Page, qr_url: str, timeout_seconds: int) -> Response:
    from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway

    return await PlaywrightScoutingEventGateway._fetch_schedule_on_page(page, qr_url, timeout_seconds)
```

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -q
```

Expected: PASS. The new `tests/characterization/conftest.py` opt-in fixture is what keeps every
existing `ACQ-*` case green — without it this step would fail with `ExternalNetworkBlocked`.

- [ ] **Step 7: Commit**

```bash
git add src/scoutmb/ports/scoutevent.py src/scoutmb/adapters/scoutevent tests/unit/scoutevent tests/characterization/conftest.py scout_schedule_cli.py
git commit -m "feat(gateway): extract Playwright navigation gateway, wire NET-WIRE-002"
```

---

## Task B4.2: HTTP requirement gateway with schema-drift validation

**Goal:** Extract `post_requirement` behind the gateway's `fetch_requirements`, wire
`NET-WIRE-001`, land `ACQ-REQ-004`, and preserve HTML description cleaning + the requirement
envelope's own failure-status check.

**Files:**
- Create: `src/scoutmb/adapters/scoutevent/http_gateway.py`,
  `src/scoutmb/adapters/scoutevent/schema.py`, `tests/parity/conftest.py`,
  `tests/integration/conftest.py`, `tests/unit/scoutevent/conftest.py` (the egress opt-in
  fixture from B4.1 Step 1, copied to the three directories this task's own new tests live under
  that B4.1 didn't already cover)
- Modify: `scout_schedule_cli.py` (`post_requirement` becomes a thin wrapper)
- Test: `tests/unit/scoutevent/test_http_gateway.py`, `tests/unit/scoutevent/test_schema.py`

**Acceptance Criteria:**
- [ ] `fetch_requirement_payload` calls `assert_egress_allowed("scoutingevent.com")` before
      `page.evaluate`, and returns the **full** requirement envelope (status + data)
- [ ] A requirement row with only `MERIT_BADGE_NAME` set raises `ScoutingEventSchemaDrift`
      naming both missing fields, with a bounded (`<=300` char) sample that has any key whose
      name contains `cookie`/`session`/`token`/`auth` (case-insensitive) redacted before
      truncation — not merely truncated
- [ ] `validate_requirement_row`'s `description` field is `clean_html_description`-cleaned, not
      the raw `REQ_DESCR` string
- [ ] A row carrying every field the legacy code reads still validates and round-trips
      identically to `RequirementRecord` construction

**Verify:** `uv run pytest tests/unit/scoutevent -q` → PASS

**Recovery:** Keep `post_requirement`'s current body (unconditional coercion); leave
`fetch_requirement_payload`/`validate_requirement_row` unreferenced.

**Steps:**

- [ ] **Step 1: Add the egress opt-in fixture to this task's new test directories**

```python
# tests/unit/scoutevent/conftest.py
# (identical to tests/characterization/conftest.py from Task B4.1 Step 1 -- copied, not
# imported, matching how tests/conftest.py-style fixtures are scoped per-directory elsewhere
# in this suite)
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _allow_synthetic_scoutingevent_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
```

`tests/parity/conftest.py` and `tests/integration/conftest.py` are the same four lines — needed
now because this task's `test_http_gateway.py` lives under `tests/unit/scoutevent/` (already
covered by B4.1 Step 1) but Tasks B5.4/B5.5 add tests under `tests/parity/`/`tests/integration/`
that will need this same opt-in; adding the two extra `conftest.py` files here keeps all five
scoped-fixture files created together rather than split confusingly across tasks.

- [ ] **Step 2: Write the schema-drift unit test**

```python
# tests/unit/scoutevent/test_schema.py
"""ACQ-REQ-004: a requirement row missing an identity field fails closed instead of being
silently coerced to blanks. Every other field keeps today's coercion, INCLUDING HTML cleaning of
the description via clean_html_description -- dropping that would regress every ACQ-REQ-* case
that carries HTML in REQ_DESCR."""

from __future__ import annotations

import pytest

from scoutmb.adapters.scoutevent.schema import (
    ScoutingEventSchemaDrift,
    validate_requirement_row,
)


def test_missing_identity_fields_raises_schema_drift() -> None:
    with pytest.raises(ScoutingEventSchemaDrift) as exc_info:
        validate_requirement_row({"MERIT_BADGE_NAME": "Chess"})

    err = exc_info.value
    assert err.profile == "requirement_row"
    assert set(err.missing_fields) == {"requirement_id", "requirement_number"}
    assert len(err.sample) <= 300


def test_well_formed_row_validates() -> None:
    row = {
        "MERIT_BADGE_NAME": "Chess",
        "MDM_LKP_BADGE_REQ_ID": "77",
        "MDM_LKP_BADGE_REQ_TYPE_ID": "2",
        "REQ_NBR_WEB_DISPLAY": "#1",
        "REQ_DESCR": "Do the thing<br>Line two",
        "COMPLETED_REQ_FLAG": "1",
    }
    validated = validate_requirement_row(row)
    assert validated["requirement_id"] == "77"
    assert validated["requirement_number"] == "#1"
    assert validated["description"] == "Do the thing\nLine two"


def test_req_nbr_fallback_satisfies_the_requirement_number_field() -> None:
    """Legacy prefers REQ_NBR_WEB_DISPLAY but falls back to REQ_NBR -- that fallback is NOT
    drift, it's a known dual representation, so either one present must validate."""
    row = {"MDM_LKP_BADGE_REQ_ID": "77", "REQ_NBR": "#2"}
    validated = validate_requirement_row(row)
    assert validated["requirement_number"] == "#2"


def test_sample_redacts_known_sensitive_key_names() -> None:
    with pytest.raises(ScoutingEventSchemaDrift) as exc_info:
        validate_requirement_row({"SESSION_COOKIE": "s3cr3t-value-should-not-leak"})
    assert "s3cr3t-value-should-not-leak" not in exc_info.value.sample
    assert "REDACTED" in exc_info.value.sample


def test_sample_stays_bounded_even_when_huge() -> None:
    huge_description = "x" * 5000
    with pytest.raises(ScoutingEventSchemaDrift) as exc_info:
        validate_requirement_row({"REQ_DESCR": huge_description})
    assert len(exc_info.value.sample) <= 300
```

Run: `uv run pytest tests/unit/scoutevent/test_schema.py -v` → FAIL (module doesn't exist)

- [ ] **Step 3: Write the schema validator, with HTML cleaning and key-name redaction**

```python
# src/scoutmb/adapters/scoutevent/schema.py
"""The schema-drift boundary (ACQ-REQ-004, D22). Two required identity fields; every other
field keeps the legacy str(x or "") / truthy() coercion from core/output_schemas.py; description
is clean_html_description-cleaned, matching process_scout's existing construction exactly
(scout_schedule_cli.py:459) -- dropping that would leave every requirement description carrying
raw <br> tags and HTML entities instead of the cleaned text the rest of the codebase relies on.

clean_html_description is duplicated here rather than imported, matching the precedent already
established between scout_schedule_cli.py and features/reporting/service.py's own
_clean_html_description (that module's docstring: 'duplicate scout_schedule_cli.py's same-named
functions rather than importing them... kept in lockstep by inspection') -- this module is a
THIRD copy for the same reason: it must not import back from the flat script, and the package
has no shared home for this one small helper yet.
"""

from __future__ import annotations

import html
import re
from typing import Any

from scoutmb.errors import ScoutmbError

_SAMPLE_LIMIT = 300
_SENSITIVE_KEY_MARKERS = ("COOKIE", "SESSION", "TOKEN", "AUTH")


class ScoutingEventSchemaDrift(ScoutmbError):
    """A requirement row from ScoutingEvent is missing a field this build treats as required.
    Carries a bounded sample with any key whose name looks sensitive redacted -- never the raw
    payload, which may carry other rows' data alongside the offending one."""

    def __init__(self, *, profile: str, missing_fields: tuple[str, ...], sample: str) -> None:
        self.profile = profile
        self.missing_fields = missing_fields
        self.sample = sample[:_SAMPLE_LIMIT]
        super().__init__(
            f"{profile} is missing required field(s) {', '.join(missing_fields)}: {self.sample}"
        )


def _redacted_sample(row: dict[str, Any]) -> str:
    """repr() of the row with any value whose KEY name contains a sensitive marker replaced by
    'REDACTED' before truncation -- truncation alone (an earlier draft's only protection) still
    lets a sensitive field's value leak if it happens to sort near the start of the dict."""
    redacted = {
        key: "REDACTED" if any(marker in key.upper() for marker in _SENSITIVE_KEY_MARKERS) else value
        for key, value in row.items()
    }
    return repr(redacted)


def _text(value: Any) -> str:
    return str(value or "")


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _clean_html_description(value: str) -> str:
    """Exact mirror of scout_schedule_cli.clean_html_description (lines 208-214)."""
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def validate_requirement_row(row: dict[str, Any]) -> dict[str, Any]:
    """Raise ScoutingEventSchemaDrift if requirement_id or requirement_number cannot be
    resolved; otherwise return the same field set process_scout already builds a
    RequirementRecord from, coerced exactly as core/output_schemas.py does, with description
    cleaned exactly as process_scout already cleans it."""
    missing: list[str] = []

    requirement_id = _text(row.get("MDM_LKP_BADGE_REQ_ID"))
    if not requirement_id:
        missing.append("requirement_id")

    requirement_number = _text(row.get("REQ_NBR_WEB_DISPLAY")) or _text(row.get("REQ_NBR"))
    if not requirement_number:
        missing.append("requirement_number")

    if missing:
        raise ScoutingEventSchemaDrift(
            profile="requirement_row", missing_fields=tuple(missing), sample=_redacted_sample(row)
        )

    return {
        "merit_badge_name": _text(row.get("MERIT_BADGE_NAME")),
        "requirement_id": requirement_id,
        "requirement_type_id": _text(row.get("MDM_LKP_BADGE_REQ_TYPE_ID")),
        "requirement_number": requirement_number,
        "description": _clean_html_description(_text(row.get("REQ_DESCR"))),
        "completed_requirement": _flag(row.get("COMPLETED_REQ_FLAG")),
        "completed_class": _flag(row.get("COMPLETED_CLASS_FLAG")),
        "requirement_on_event": _flag(row.get("REQ_ON_EVENT")),
        "present_days": _text(row.get("PRESENT_DAYS")).strip(),
    }
```

- [ ] **Step 4: Write the HTTP gateway function, egress-checked, returning the full envelope**

```python
# src/scoutmb/adapters/scoutevent/http_gateway.py
"""The 'HTTP' seam (D22, NET-WIRE-001) -- so named because it is a single request/response
round trip, even though it is issued via Playwright's in-page fetch() rather than a Python HTTP
client. That stays true to how the site's session cookie works: the request must originate from
the authenticated page context, so there is no seam for a separate Python HTTP client here.

Returns the FULL requirement envelope (status + data), unmodified -- process_scout today checks
requirement_payload["status"]["status"] independently of what's inside data
(scout_schedule_cli.py:441) and writes the complete envelope to raw/ (line 437). Stripping this
down to just `data` would silently drop both behaviors; the CALLER (AcquisitionService) owns
interpreting status and validating each row, matching today's split.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from scoutmb.network_policy import assert_egress_allowed

AJAX_URL = "https://scoutingevent.com/mobile/inc/ajax_mobile.php"


async def fetch_requirement_payload(
    page: Any, attendee_id: str, class_p4_id: str
) -> dict[str, Any]:
    assert_egress_allowed(urlparse(AJAX_URL).hostname or "")

    result = await page.evaluate(
        """async ({url, attendeeId, classP4Id}) => {
            const body = new URLSearchParams({
                getClassRequirement: 'true',
                classP4ID: classP4Id,
                attendeeID: attendeeId,
                TimeStamp: new Date().toString()
            });
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: body.toString()
            });
            return { ok: response.ok, status: response.status, text: await response.text() };
        }""",
        {"url": AJAX_URL, "attendeeId": attendee_id, "classP4Id": class_p4_id},
    )
    if not result["ok"]:
        raise RuntimeError(f"Requirement request returned HTTP {result['status']}")
    try:
        return json.loads(result["text"])
    except json.JSONDecodeError as exc:
        preview = result["text"][:300].replace("\n", " ")
        raise RuntimeError(f"Requirement response was not JSON: {preview}") from exc
```

```python
# tests/unit/scoutevent/test_http_gateway.py
from __future__ import annotations

import pytest

from scoutmb.adapters.scoutevent.http_gateway import fetch_requirement_payload
from scoutmb.errors import ExternalNetworkBlocked


@pytest.mark.matrix_case(case_id="NET-WIRE-001", context_id="net-wire", lane="default")
async def test_egress_check_runs_before_evaluate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)

    class _ExplodingPage:
        async def evaluate(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("evaluate() must not be called when egress is blocked")

    with pytest.raises(ExternalNetworkBlocked):
        await fetch_requirement_payload(_ExplodingPage(), "A1", "C1")


async def test_full_envelope_is_returned_unmodified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    import json as _json

    class _FakePage:
        async def evaluate(self, *args: object, **kwargs: object) -> dict[str, object]:
            payload = {"status": {"status": 1}, "data": [{"MDM_LKP_BADGE_REQ_ID": "1"}]}
            return {"ok": True, "status": 200, "text": _json.dumps(payload)}

    result = await fetch_requirement_payload(_FakePage(), "A1", "C1")
    assert result == {"status": {"status": 1}, "data": [{"MDM_LKP_BADGE_REQ_ID": "1"}]}
```

- [ ] **Step 5: Point the legacy shim at the gateway**

```python
# scout_schedule_cli.py -- replace post_requirement's body
async def post_requirement(page: Page, attendee_id: str, class_p4_id: str) -> dict[str, Any]:
    from scoutmb.adapters.scoutevent.http_gateway import fetch_requirement_payload

    return await fetch_requirement_payload(page, attendee_id, class_p4_id)
```

Note: `validate_requirement_row` is **not** wired into `process_scout` in this task —
`process_scout` still does its own inline coercion today, and rewiring it to call the
validator (so `ACQ-REQ-004`'s row is actually rejected end to end) is Task B5.4, once
`features/acquisition/service.py` exists to own that decision. This task lands the validator and
the egress check as independently-tested units first.

- [ ] **Step 6: Run and commit**

```bash
uv run pytest tests/unit/scoutevent tests/characterization/test_acquisition_matrix.py tests/architecture -q
```

```bash
git add src/scoutmb/adapters/scoutevent/http_gateway.py src/scoutmb/adapters/scoutevent/schema.py tests/unit/scoutevent tests/parity/conftest.py tests/integration/conftest.py scout_schedule_cli.py
git commit -m "feat(gateway): extract HTTP requirement gateway + schema-drift validator, wire NET-WIRE-001"
```

---

## Task B5.1: Freeze `ScoutResult` — `process_scout` accumulates then constructs once

**Goal:** `process_scout` builds the package's frozen, tuple-based `scoutmb.core.models.ScoutResult`
directly; the legacy `scout_schedule_cli.ScoutResult` class becomes a re-export.

**Files:**
- Modify: `scout_schedule_cli.py` (`ScoutResult` alias, `process_scout` body)
- Test: `tests/parity/test_models_parity.py` (extend), `tests/unit/test_process_scout_frozen.py`

**Acceptance Criteria:**
- [ ] `scout_schedule_cli.ScoutResult is scoutmb.core.models.ScoutResult`
- [ ] `process_scout` never calls `.append` on a `ScoutResult` field — classes/requirements/errors
      accumulate into local lists, `ScoutResult(...)` is constructed exactly once per scout
- [ ] Every `process`/`raw`/`asset` `ACQ-*` case still passes (this is a pure internal
      restructuring of `process_scout`, not a behavior change)
- [ ] `dataclasses.replace(result, errors=(*result.errors, "x"))` works (proves frozen + tuple)

**Verify:** `uv run pytest tests/parity/test_models_parity.py tests/unit/test_process_scout_frozen.py tests/characterization/test_acquisition_matrix.py -q` → PASS

**Recovery:** Revert `ScoutResult` to its own mutable class; the frozen package shape stays
available for direct use elsewhere, just not aliased.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_process_scout_frozen.py
"""B5 Task 1: process_scout must build the frozen, tuple-based ScoutResult -- not the legacy
mutable list-based one -- so `.classes`/`.requirements`/`.errors` are tuples and the object
supports dataclasses.replace()."""

from __future__ import annotations

import dataclasses

import pytest

import scout_schedule_cli as legacy
from scoutmb.core.models import ScoutResult as PackageScoutResult


def test_scout_result_is_the_frozen_package_shape() -> None:
    assert legacy.ScoutResult is PackageScoutResult


def test_scout_result_instances_are_frozen_and_tuple_backed() -> None:
    result = legacy.ScoutResult(name="Avery", qr_url="https://x")
    assert isinstance(result.classes, tuple)
    assert isinstance(result.requirements, tuple)
    assert isinstance(result.errors, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.errors = ("boom",)  # type: ignore[misc]
    replaced = dataclasses.replace(result, errors=(*result.errors, "boom"))
    assert replaced.errors == ("boom",)
```

Run: `uv run pytest tests/unit/test_process_scout_frozen.py -v` → FAIL
(`legacy.ScoutResult is PackageScoutResult` is False; the legacy class is a separate mutable one)

- [ ] **Step 2: Re-point the `ScoutResult` alias**

```python
# scout_schedule_cli.py -- replace the @dataclass(slots=True) class ScoutResult block (lines 83-90)
from scoutmb.core.models import ScoutResult  # noqa: F401 - legacy public surface
```

- [ ] **Step 3: Rewrite `process_scout` to accumulate locally**

`ScoutResult` no longer has mutable `.classes`/`.requirements`/`.errors` to `.append` onto, so
`process_scout` accumulates into local lists across the whole function body and constructs the
record once, right before returning — including on the exception path, where today's code does
`result.errors.append(str(exc))` after the object already exists. This is a **pure mechanical
restructuring**: every field, coercion, and control-flow branch stays exactly as it is today —
`process_scout`'s own body is not yet routed through the gateway (that happens implicitly, since
Task B4.1/B4.2 already re-pointed `navigate_and_trigger_schedule`/`post_requirement`'s bodies at
the gateway; `process_scout` itself still calls those two functions by name, unchanged).

```python
# scout_schedule_cli.py -- replace process_scout's body
async def process_scout(
    browser: Browser,
    scout: ScoutInput,
    args: argparse.Namespace,
    raw_dir: Path,
    run_identity: RunIdentity | None = None,
) -> ScoutResult:
    run_identity = run_identity or RunIdentity()
    context: BrowserContext = await browser.new_context(ignore_https_errors=True)

    if not args.allow_dead_assets:
        async def block_dead_assets(route: Any) -> None:
            try:
                hostname = re.sub(r"^https?://", "", route.request.url).split("/", 1)[0].split(":", 1)[0]
                if hostname in DEAD_ASSET_HOSTS:
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                await route.continue_()
        await context.route("**/*", block_dead_assets)

    page = await context.new_page()
    page.set_default_timeout(args.timeout * 1000)
    page.on("pageerror", lambda error: print(f"    browser JS error: {error}", file=sys.stderr))

    name = scout.name or "Unknown Scout"
    attendee_id = ""
    classes: list[ClassRecord] = []
    requirements: list[RequirementRecord] = []
    errors: list[str] = []

    try:
        schedule_response = await navigate_and_trigger_schedule(page, scout.url, args.timeout)
        request_values = form_values(schedule_response.request.post_data)
        attendee_id = request_values.get("attendeeID", "")
        if not attendee_id:
            raise RuntimeError("The schedule request did not contain attendeeID")

        name = await discover_name(page, scout.name)

        schedule_payload = await schedule_response.json()
        raw_dir.mkdir(parents=True, exist_ok=True)
        output_id = run_identity.output_id(AttendeeId.parse(attendee_id, name))
        slug = attendee_filename_stem(name, output_id)
        (raw_dir / f"{slug}-schedule.json").write_text(
            json.dumps(schedule_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if int(schedule_payload.get("status", {}).get("status", 0)) != 1:
            raise RuntimeError(f"Schedule API returned failure: {schedule_payload.get('status')}")

        schedule_rows = schedule_payload.get("data") or []
        deduped_rows: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in schedule_rows:
            key = str(item.get("classP4ID") or "")
            if not key:
                key = f"__no_id_{len(order)}"
                deduped_rows[key] = item
                order.append(key)
            elif key not in deduped_rows:
                deduped_rows[key] = item
                order.append(key)
            elif truthy(item.get("CLASS_COMPLETED")) and not truthy(deduped_rows[key].get("CLASS_COMPLETED")):
                deduped_rows[key] = item
        schedule_rows = [deduped_rows[key] for key in order]

        for item in schedule_rows:
            raw_class_name = str(item.get("CLASS_NAME") or "")
            class_record = ClassRecord(
                scout_name=name,
                attendee_id=attendee_id,
                class_number=str(item.get("CLASS_NBR") or ""),
                class_p4_id=str(item.get("classP4ID") or ""),
                class_name=str(item.get("CLASS_NAME_ONLY") or ""),
                days=days_from_class_name(raw_class_name),
                period_name=str(item.get("PERIOD_NAME") or ""),
                start_time=str(item.get("CLASS_STIME") or ""),
                start_time_24h=str(item.get("STIME") or ""),
                location=str(item.get("LOCATION_ROOM_NAME") or ""),
                has_requirements=truthy(item.get("HAS_REQ")),
                class_completed=truthy(item.get("CLASS_COMPLETED")),
                raw_class_name=raw_class_name,
            )
            classes.append(class_record)

            if not class_record.class_p4_id:
                continue

            requirement_payload: dict[str, Any] | None = None
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    requirement_payload = await post_requirement(
                        page, attendee_id, class_record.class_p4_id
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    await page.wait_for_timeout(500 * attempt)

            if requirement_payload is None:
                errors.append(f"{class_record.class_name}: requirement request failed: {last_error}")
                continue

            (raw_dir / f"{slug}-{safe_slug(class_record.class_number or class_record.class_p4_id)}-requirements.json").write_text(
                json.dumps(requirement_payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            if int(requirement_payload.get("status", {}).get("status", 0)) != 1:
                errors.append(
                    f"{class_record.class_name}: requirement API returned failure: "
                    f"{requirement_payload.get('status')}"
                )
                continue

            for req in requirement_payload.get("data") or []:
                requirements.append(
                    RequirementRecord(
                        scout_name=name,
                        attendee_id=attendee_id,
                        class_number=class_record.class_number,
                        class_p4_id=class_record.class_p4_id,
                        merit_badge_name=str(req.get("MERIT_BADGE_NAME") or ""),
                        requirement_id=str(req.get("MDM_LKP_BADGE_REQ_ID") or ""),
                        requirement_type_id=str(req.get("MDM_LKP_BADGE_REQ_TYPE_ID") or ""),
                        requirement_number=str(req.get("REQ_NBR_WEB_DISPLAY") or req.get("REQ_NBR") or ""),
                        description=clean_html_description(str(req.get("REQ_DESCR") or "")),
                        completed_requirement=truthy(req.get("COMPLETED_REQ_FLAG")),
                        completed_class=truthy(req.get("COMPLETED_CLASS_FLAG")),
                        requirement_on_event=truthy(req.get("REQ_ON_EVENT")),
                        present_days=str(req.get("PRESENT_DAYS") or "").strip(),
                    )
                )

            if args.request_delay_ms > 0:
                await page.wait_for_timeout(args.request_delay_ms)

    except Exception as exc:
        errors.append(str(exc))
    finally:
        await context.close()

    return ScoutResult(
        name=name,
        qr_url=scout.url,
        attendee_id=attendee_id,
        classes=tuple(classes),
        requirements=tuple(requirements),
        errors=tuple(errors),
    )
```

- [ ] **Step 4: Run and commit**

```bash
uv run pytest -q
```

```bash
git add scout_schedule_cli.py tests/unit/test_process_scout_frozen.py tests/parity/test_models_parity.py
git commit -m "refactor(acquisition): freeze ScoutResult, process_scout accumulates then constructs once"
```

---

## Task B5.2: Retry policy + circuit breaker

**Goal:** A standalone, injectable `RetryPolicy` collaborator keeps the characterized ×3
500/1000/1500ms backoff (including the wait after the third, final attempt) and adds a
consecutive-failure circuit breaker — landing `ACQ-BREAKER-001/002/003`. Its check/record methods
are exercised here as pure state; **who calls them, and how often, is Task B5.5's job** — a
single `RetryPolicy` instance must be shared across an entire run's scouts for the breaker to
mean anything, which this task's unit tests prove in isolation without yet wiring a caller.

**Files:**
- Create: `src/scoutmb/features/acquisition/__init__.py`,
  `src/scoutmb/features/acquisition/retry.py`
- Test: `tests/unit/acquisition/test_retry_policy.py`

**Acceptance Criteria:**
- [ ] Below the failure threshold, the breaker stays closed and reports so
- [ ] At the threshold, the breaker opens and reports open — no further attempts are permitted
      until a success resets it
- [ ] A single success resets the consecutive-failure count to zero (`ACQ-BREAKER-003`)
- [ ] Retry delay uses the injected `Sleeper`/`Jitter` ports, never `asyncio.sleep`/`time.sleep`
      directly, and stays `500 * attempt` ms for attempts 1-3 (including attempt 3) with jitter
      added on top, not replacing the characterized base delay

**Verify:** `uv run pytest tests/unit/acquisition/test_retry_policy.py -q` → PASS

**Recovery:** Leave `RetryPolicy` unreferenced; `process_scout`'s inline `for attempt in
range(1, 4)` loop stays the live path until B5.4/B5.5 wire it in.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/acquisition/test_retry_policy.py
"""ACQ-BREAKER-001/002/003: consecutive-failure breaker. Below threshold stays closed; at
threshold opens; a success resets the count. The Sleeper/Jitter ports are fakes here -- no real
delay ever occurs in this test."""

from __future__ import annotations

import pytest

from scoutmb.features.acquisition.retry import BreakerOpen, RetryPolicy


class _RecordingSleeper:
    def __init__(self) -> None:
        self.slept_ms: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept_ms.append(seconds * 1000)

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


@pytest.mark.matrix_case(case_id="ACQ-BREAKER-001", context_id="breaker", lane="default")
async def test_stays_closed_below_threshold() -> None:
    policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=3)
    policy.record_failure()
    policy.record_failure()
    assert policy.is_open is False


@pytest.mark.matrix_case(case_id="ACQ-BREAKER-002", context_id="breaker", lane="default")
async def test_opens_at_threshold_and_rejects_further_attempts() -> None:
    policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=3)
    policy.record_failure()
    policy.record_failure()
    policy.record_failure()
    assert policy.is_open is True
    with pytest.raises(BreakerOpen):
        policy.check_closed()


@pytest.mark.matrix_case(case_id="ACQ-BREAKER-003", context_id="breaker", lane="default")
async def test_success_resets_consecutive_failures() -> None:
    policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=3)
    policy.record_failure()
    policy.record_failure()
    policy.record_success()
    policy.record_failure()
    policy.record_failure()
    assert policy.is_open is False  # would have opened at 3 consecutive without the reset


async def test_backoff_delay_is_500ms_times_attempt_including_the_third(monkeypatch) -> None:
    sleeper = _RecordingSleeper()
    policy = RetryPolicy(sleeper=sleeper, jitter=_ZeroJitter(), breaker_threshold=99)
    await policy.wait_after_failure(1)
    await policy.wait_after_failure(2)
    await policy.wait_after_failure(3)
    assert sleeper.slept_ms == [500.0, 1000.0, 1500.0]
```

Run: `uv run pytest tests/unit/acquisition/test_retry_policy.py -v` → FAIL (module doesn't exist)

- [ ] **Step 2: Implement `RetryPolicy`**

```python
# src/scoutmb/features/acquisition/__init__.py
```

```python
# src/scoutmb/features/acquisition/retry.py
"""Retry backoff (characterized, unchanged: 500ms x attempt for attempts 1-3, including the
wait after the third and final attempt) plus a consecutive-failure circuit breaker
(ACQ-BREAKER-001/002/003). Only ONE RetryPolicy instance exists per run (Task B5.5 constructs
it), so its breaker state is genuinely cumulative across scouts -- constructing a fresh instance
per scout (a bug an earlier draft of this plan had) makes the breaker permanently unable to
trip, since nothing then ever sees more than one scout's failures at a time."""

from __future__ import annotations

from dataclasses import dataclass, field

from scoutmb.errors import ScoutmbError
from scoutmb.ports.clock import Jitter, Sleeper


class BreakerOpen(ScoutmbError):
    """Consecutive failures reached the configured threshold; no further attempts are
    permitted until a success resets the count."""


@dataclass(slots=True)
class RetryPolicy:
    sleeper: Sleeper
    jitter: Jitter
    breaker_threshold: int
    _consecutive_failures: int = field(default=0, init=False)

    @property
    def is_open(self) -> bool:
        return self._consecutive_failures >= self.breaker_threshold

    def check_closed(self) -> None:
        if self.is_open:
            raise BreakerOpen(
                f"{self._consecutive_failures} consecutive failures reached the "
                f"threshold of {self.breaker_threshold}"
            )

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def record_success(self) -> None:
        self._consecutive_failures = 0

    async def wait_after_failure(self, attempt: int) -> None:
        """Named for when it is actually called -- after attempt N fails, before attempt N+1 (or
        before giving up, on the third). An earlier draft called this wait_before_attempt, which
        reads as running before EVERY attempt including the first; it never does."""
        base_seconds = (500 * attempt) / 1000
        jittered = base_seconds + self.jitter.jitter(0, base_seconds * 0.1)
        await self.sleeper.sleep(jittered)
```

Note: the test's fake pins jitter to zero (`_ZeroJitter` returns `low`, i.e. `0`) so the jittered
delay collapses to exactly the base delay and the assertion on `sleeper.slept_ms` stays exact —
a non-zero jitter would make that specific assertion flaky by construction.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest tests/unit/acquisition -q
```

```bash
git add src/scoutmb/features/acquisition tests/unit/acquisition/test_retry_policy.py
git commit -m "feat(acquisition): add RetryPolicy with consecutive-failure circuit breaker"
```

---

## Task B5.3: Resumable checkpoints

**Goal:** A `CheckpointStore` port + `AtomicFileCheckpointStore` adapter persist which scouts
(keyed by QR URL) are already complete and the attendee→output-UUID map, so a resumed run skips
completed scouts and reuses their UUIDs — landing `ACQ-RESUME-001/002/003/004`. The checkpoint
payload is genuinely immutable (not merely typed `Mapping`), `CorruptCheckpoint` subclasses
`ScoutmbError`, and `load()` rejects every malformed shape a hand-edited or corrupted file could
take, not just a wrong version number.

**Files:**
- Create: `src/scoutmb/ports/checkpoint_store.py`, `src/scoutmb/adapters/files/checkpoint.py`
- Test: `tests/unit/acquisition/test_checkpointing.py`

**Acceptance Criteria:**
- [ ] A run with no prior checkpoint file creates one on first save
- [ ] A scout whose QR URL is in `completed_urls` is skipped by the resume check
- [ ] The attendee-id→output-id map round-trips through save/load unchanged, and the loaded
      `Checkpoint.output_ids` cannot be mutated by mutating a dict the caller still holds a
      reference to
- [ ] A checkpoint file with an unreadable/wrong-shaped body — including a `completed_urls` that
      is a string, an `output_ids` that is a list, non-string keys or values inside `output_ids`,
      `version: true` (a JSON boolean, which Python's `json` module deserializes to `True`, an
      `int` subclass equal to `1` — the exact hazard `core/output_schemas.py`'s own
      `check_schema_version` already documents and guards against), or invalid UTF-8 — raises
      `CorruptCheckpoint` from `load()` rather than being partially trusted
- [ ] `CorruptCheckpoint` subclasses `ScoutmbError`
- [ ] The save path is atomic (reuses `atomic_write_text`'s same-dir-temp-then-replace contract);
      a save that fails mid-replace leaves the prior checkpoint's bytes intact

**Verify:** `uv run pytest tests/unit/acquisition/test_checkpointing.py -q` → PASS

**Recovery:** Leave the checkpoint store unreferenced; no run writes a checkpoint file yet.

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/acquisition/test_checkpointing.py
"""ACQ-RESUME-001/002/003/004: checkpoint creation, skip-on-resume, UUID persistence, and
fail-closed on corruption -- INCLUDING type-confused shapes a hand-edited or partially-written
file could take, not just a wrong version number. No fake here -- these exercise the real
AtomicFileCheckpointStore against tmp_path, since the whole point is the on-disk round trip."""

from __future__ import annotations

import json
from types import MappingProxyType

import pytest

from scoutmb.adapters.files.atomic import atomic_write_text
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.errors import ScoutmbError
from scoutmb.ports.checkpoint_store import Checkpoint, CorruptCheckpoint


def test_corrupt_checkpoint_is_a_scoutmb_error() -> None:
    assert issubclass(CorruptCheckpoint, ScoutmbError)


@pytest.mark.matrix_case(case_id="ACQ-RESUME-001", context_id="resume", lane="default")
def test_fresh_run_has_no_checkpoint(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    assert store.load() is None


def test_save_then_load_round_trips(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint = Checkpoint(
        version=1,
        completed_urls=("https://x/a", "https://x/b"),
        output_ids={"attendee-1": "11111111-1111-4111-8111-111111111111"},
    )
    store.save(checkpoint)

    loaded = store.load()
    assert loaded == checkpoint


def test_output_ids_is_genuinely_immutable(tmp_path) -> None:
    """A dataclass's frozen=True freezes the FIELD REFERENCE, not a mutable dict sitting behind
    it -- Checkpoint.output_ids must be an actual read-only view, not merely typed Mapping."""
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    mutable_source = {"attendee-1": "uuid-1"}
    checkpoint = Checkpoint(version=1, completed_urls=(), output_ids=mutable_source)
    mutable_source["attendee-1"] = "mutated-after-construction"
    assert checkpoint.output_ids["attendee-1"] == "uuid-1"  # __post_init__ copied, not aliased

    assert isinstance(checkpoint.output_ids, MappingProxyType)
    with pytest.raises(TypeError):
        checkpoint.output_ids["attendee-1"] = "should-not-be-settable"  # type: ignore[index]


@pytest.mark.matrix_case(case_id="ACQ-RESUME-002", context_id="resume", lane="default")
def test_completed_url_is_recognized_on_resume(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    store.save(Checkpoint(version=1, completed_urls=("https://x/a",), output_ids={}))

    loaded = store.load()
    assert loaded is not None
    assert "https://x/a" in loaded.completed_urls
    assert "https://x/b" not in loaded.completed_urls


@pytest.mark.matrix_case(case_id="ACQ-RESUME-003", context_id="resume", lane="default")
def test_output_id_map_survives_a_reload(tmp_path) -> None:
    store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    store.save(
        Checkpoint(version=1, completed_urls=(), output_ids={"attendee-1": "same-uuid"})
    )
    reloaded = AtomicFileCheckpointStore(tmp_path / "checkpoint.json").load()
    assert reloaded is not None
    assert reloaded.output_ids["attendee-1"] == "same-uuid"


@pytest.mark.matrix_case(case_id="ACQ-RESUME-004", context_id="resume", lane="default")
def test_corrupt_json_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = AtomicFileCheckpointStore(path)
    with pytest.raises(CorruptCheckpoint):
        store.load()


def test_wrong_version_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"version": 999, "completed_urls": [], "output_ids": {}}), encoding="utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_boolean_version_does_not_masquerade_as_one(tmp_path) -> None:
    """json.dumps(True) is the JSON literal `true`; json.loads('true') deserializes to Python's
    True, and `True == 1` since bool is an int subclass -- a naive `version != 1` check would
    silently accept this. core/output_schemas.py's check_schema_version already documents and
    guards against exactly this; the checkpoint loader must apply the same discipline."""
    path = tmp_path / "checkpoint.json"
    path.write_text('{"version": true, "completed_urls": [], "output_ids": {}}', encoding="utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_missing_required_key_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_completed_urls_wrong_type_fails_closed(tmp_path) -> None:
    """A string is iterable, so a naive tuple(data["completed_urls"]) would silently produce a
    tuple of individual CHARACTERS instead of raising -- this must fail closed instead."""
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": "https://x/a", "output_ids": {}}),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_output_ids_wrong_type_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": [], "output_ids": ["not", "a", "dict"]}),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_output_ids_non_string_value_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 1, "completed_urls": [], "output_ids": {"attendee-1": 12345}}),
        encoding="utf-8",
    )
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_invalid_utf8_fails_closed(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_bytes(b"\xff\xfe\x00\x01not valid utf-8")
    with pytest.raises(CorruptCheckpoint):
        AtomicFileCheckpointStore(path).load()


def test_save_failure_preserves_prior_bytes(tmp_path, monkeypatch) -> None:
    """Reuses atomic_write_text's own contract: a failed os.replace leaves the previous file
    untouched. This test proves the CHECKPOINT save path actually benefits from that contract,
    not merely that atomic_write_text does (already proven elsewhere for report artifacts)."""
    path = tmp_path / "checkpoint.json"
    store = AtomicFileCheckpointStore(path)
    store.save(Checkpoint(version=1, completed_urls=("https://x/a",), output_ids={}))
    original_bytes = path.read_bytes()

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("scoutmb.adapters.files.atomic.os.replace", _boom)
    with pytest.raises(OSError):
        store.save(Checkpoint(version=1, completed_urls=("https://x/a", "https://x/b"), output_ids={}))

    assert path.read_bytes() == original_bytes
```

Run: `uv run pytest tests/unit/acquisition/test_checkpointing.py -v` → FAIL (modules don't exist)

- [ ] **Step 2: Define the port, with a genuinely immutable payload**

```python
# src/scoutmb/ports/checkpoint_store.py
"""The seam a checkpoint adapter implements (ACQ-RESUME). One real implementation (an atomic
JSON file) and this Protocol, matching every other port in this codebase -- not the generic
ports/storage.py the Phase B spec declines to create, since this is fixed to one schema rather
than a general filesystem abstraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from scoutmb.errors import ScoutmbError

CHECKPOINT_VERSION = 1


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """frozen=True freezes the FIELD REFERENCE, not a mutable dict sitting behind it -- so
    __post_init__ copies output_ids into a MappingProxyType, making the exposed mapping a
    genuine read-only view rather than a typed-but-mutable dict a caller could still corrupt
    through their own retained reference to the mapping they passed in."""

    version: int
    completed_urls: tuple[str, ...]
    output_ids: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_ids", MappingProxyType(dict(self.output_ids)))


class CorruptCheckpoint(ScoutmbError):
    """A checkpoint file exists but cannot be trusted: unreadable, wrong-shaped, or an
    unsupported version. Resuming from it is refused rather than guessed at. Subclasses
    ScoutmbError like every other exception this package raises (errors.py:6)."""


class CheckpointStore(Protocol):
    def load(self) -> Checkpoint | None: ...
    def save(self, checkpoint: Checkpoint) -> None: ...
```

- [ ] **Step 3: Implement the atomic-file adapter, validating every field's shape**

```python
# src/scoutmb/adapters/files/checkpoint.py
"""Atomic JSON checkpoint file (ACQ-RESUME). Reuses atomic_write_text's same-dir-temp-then-
replace contract (D11) -- a failed save never truncates the previous checkpoint.

load() validates every field's TYPE, not just presence -- a hand-edited or partially-written
file can have the right keys with the wrong shapes (a string where a list is expected, a bool
where an int is expected), and each of those must fail closed rather than silently produce
garbage (json.loads("...")'s dynamic typing means Python raises nothing on its own for most of
these; only an explicit type check does)."""

from __future__ import annotations

import json
from pathlib import Path

from scoutmb.adapters.files.atomic import atomic_write_text
from scoutmb.ports.checkpoint_store import CHECKPOINT_VERSION, Checkpoint, CorruptCheckpoint


class AtomicFileCheckpointStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Checkpoint | None:
        if not self._path.exists():
            return None
        try:
            raw_bytes = self._path.read_bytes()
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorruptCheckpoint(f"{self._path} is not valid UTF-8") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CorruptCheckpoint(f"{self._path} is not valid JSON") from exc

        if not isinstance(data, dict):
            raise CorruptCheckpoint(f"{self._path} does not contain a JSON object")

        version = data.get("version")
        # type(version) is int (not isinstance, not ==) is deliberate -- bool is an int
        # subclass (isinstance(True, int) is True, True == 1 is True), and core/output_schemas.py's
        # check_schema_version already documents this exact hazard for the same reason.
        if type(version) is not int or version != CHECKPOINT_VERSION:
            raise CorruptCheckpoint(
                f"{self._path} has version {version!r}, this build reads {CHECKPOINT_VERSION!r}"
            )

        try:
            raw_completed_urls = data["completed_urls"]
            raw_output_ids = data["output_ids"]
        except KeyError as exc:
            raise CorruptCheckpoint(f"{self._path} is missing required key {exc}") from exc

        if not isinstance(raw_completed_urls, list) or not all(
            isinstance(url, str) for url in raw_completed_urls
        ):
            raise CorruptCheckpoint(f"{self._path}'s completed_urls must be a list of strings")

        if not isinstance(raw_output_ids, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in raw_output_ids.items()
        ):
            raise CorruptCheckpoint(f"{self._path}'s output_ids must be a string-to-string object")

        return Checkpoint(
            version=version,
            completed_urls=tuple(raw_completed_urls),
            output_ids=raw_output_ids,
        )

    def save(self, checkpoint: Checkpoint) -> None:
        payload = {
            "version": checkpoint.version,
            "completed_urls": list(checkpoint.completed_urls),
            "output_ids": dict(checkpoint.output_ids),
        }
        atomic_write_text(self._path, json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/unit/acquisition/test_checkpointing.py -q
```

```bash
git add src/scoutmb/ports/checkpoint_store.py src/scoutmb/adapters/files/checkpoint.py tests/unit/acquisition/test_checkpointing.py
git commit -m "feat(acquisition): add resumable JSON checkpoint store, fail closed on corruption"
```

---

## Task B5.4: `features/acquisition/service.py` — one-scout acquisition, HAS_REQ skip, schema validation wired in

**Goal:** `AcquisitionService` handles ONE scout: opens a gateway session, dedupes classes,
fetches+validates each class's requirements with per-request retry, and returns a `ScoutResult`
matching every preserved `ACQ-*` case plus the new `ACQ-HASREQ-002` behavior — routing every
raw-file write through the injected `ArtifactSink` port, never `Path.write_text()` directly.
**This task does not touch the circuit breaker's open/closed decision or the checkpoint store —
those are batch-level concerns Task B5.5 owns.**

**Files:**
- Create: `src/scoutmb/features/acquisition/service.py`, `tests/parity/test_acquisition_parity.py`,
  `tests/integration/test_acquisition_lifecycle.py`
- Modify: `tests/matrix/cases/acquisition_cases.py` (`ACQ-HASREQ-002`'s `expected_legacy`
  changes from "issues the request" to "skips it" — the sanctioned exception)
- Test: as above, plus `tests/characterization/test_acquisition_matrix.py` stays green

**Acceptance Criteria:**
- [ ] `AcquisitionService.process(scout, ...)` returns a `ScoutResult` matching every `preserve`
      `ACQ-*` case's `expected_legacy` exactly, and the new `ACQ-HASREQ-002` expectation (skip on
      `HAS_REQ='0'`)
- [ ] The DOM-discovered name, the full schedule/requirement raw envelopes, and
      `clean_html_description`-cleaned descriptions are all preserved — the acceptance criteria
      from B4.1/B4.2 that made this possible are exercised here, not merely asserted there
- [ ] A row that fails `validate_requirement_row` produces one bounded error string in
      `ScoutResult.errors`, not a crash and not a silently-blanked `RequirementRecord`
- [ ] Every raw/ write goes through `self.sink.publish_text(...)` — no `Path.write_text()` call
      anywhere in `AcquisitionService`
- [ ] A session that raises before completing (e.g. the schedule fetch fails) still closes its
      `BrowserContext` — proven by an integration test, not inferred from the unit tests
- [ ] A synthetic case with `HAS_REQ='0'` exists and exercises the skip directly (the canonical
      corpus has none, per the spec's request-count restatement)
- [ ] `tests/parity/test_acquisition_parity.py` adds a `PackageAcquisitionRunner` mirroring
      `LegacyAcquisitionRunner`'s `process`/`raw` contexts against `AcquisitionService`, and every
      `ACQUISITION_CASES` execution key passes both runners (lane accounting rule)
- [ ] `ACQ-BREAKER-001/002/003`, `ACQ-RESUME-001/002/003/004`, and `NET-WIRE-001/002` all carry
      `classification=Classification.PRESERVE` and a non-empty `contexts` tuple (no longer
      `NEW_ACCEPTANCE`/`contexts=()` placeholders)

**Verify:** `uv run pytest tests/parity/test_acquisition_parity.py tests/integration/test_acquisition_lifecycle.py tests/characterization/test_acquisition_matrix.py tests/matrix -q` → PASS

**Recovery:** Keep `process_scout`'s inline loop as the composed default; disable
`AcquisitionService` at composition; the checkpoint/breaker/gateway units from B4/B5.1-3 stay
merged and unit-tested but unreferenced in production.

**Steps:**

- [ ] **Step 1: Add the synthetic `HAS_REQ='0'` case and restate the expectation**

Update the existing `ACQ-HASREQ-002` case so its `AcquisitionObservation.result` reflects the new
behavior — the requirement fetch is skipped entirely, so no `("req", ...)` tuple appears:

```python
    AcquisitionCase(
        _meta(
            "ACQ-HASREQ-002",
            "ACQ-HASREQ",
            "has-req-0",
            "process",
            "Slice 2b: HAS_REQ=0 now skips the requirement fetch entirely, instead of issuing "
            "it and relying on the response to be empty.",
            "scoutmb.features.acquisition.service.AcquisitionService.process",
            classification=Classification.INTENTIONAL_CHANGE,
            target_owner="Slice 2",
            target_observation="Slice 2 will skip the requirement request entirely when "
            "HAS_REQ='0', instead of issuing it and relying on the response to be empty.",
        ),
        NAME_A,
        URL_A,
        (_sched(ATTENDEE_A, _schedule_payload((_class_row(CLASS_A, has_req="0"),))),),
        AcquisitionObservation(
            result=(
                ("attendee_id", ATTENDEE_A),
                ("class", "26MB1", CLASS_A, False, False),
            )
        ),
    ),
```

Note the case's own script tuple also drops the now-unreachable `_req(...)` entry — a requirement
request that never fires has nothing to script a response for, and an unconsumed scripted
response would fail `StrictScript.assert_consumed()`.

- [ ] **Step 1b: Reclassify the nine new-acceptance rows now that each has a real test**

`CaseMetadata.execution_keys()` returns `()` unconditionally for `Classification.NEW_ACCEPTANCE`
regardless of what `contexts` holds (`tests/matrix/model.py:73-76`), so simply changing
`contexts=()` to a real tuple does nothing on its own — a new-acceptance row only enters the
executed matrix once it is reclassified, matching how `NET-POLICY-*` (a previously-nonexistent
boundary Slice 1a added) is declared: `classification` left at its `PRESERVE` default and a real
`context` given as `_meta`'s fourth positional argument.

In `tests/matrix/cases/acquisition_cases.py`, change each of the nine rows in
`NEW_ACCEPTANCE_ACQUISITION_METADATA` and `NET_WIRE_METADATA`:

```python
# tests/matrix/cases/acquisition_cases.py -- example for one row; repeat the same two-field
# change (contexts, and dropping classification/target_owner/target_observation now that the
# row is no longer a placeholder) for all nine ACQ-BREAKER-*/ACQ-RESUME-*/NET-WIRE-* entries.
CaseMetadata(
    case_id="ACQ-BREAKER-001",
    axis_id="ACQ-BREAKER",
    member="below-threshold",
    domain=Domain.ACQUISITION,
    classification=Classification.PRESERVE,
    evidence=EvidenceKind.PROPERTY_BOUNDARY,
    rationale="The acquisition retry policy tracks consecutive failures and stays closed "
    "(keeps attempting scouts) while the count is below the configured threshold.",
    contexts=("breaker",),
    evidence_reference="tests/unit/acquisition/test_retry_policy.py::"
    "test_stays_closed_below_threshold",
),
```

Each row's `contexts` value must match the `context_id` the corresponding
`@pytest.mark.matrix_case(...)` decorator declares: `ACQ-BREAKER-001/002/003` → `"breaker"`;
`ACQ-RESUME-001/002/003/004` → `"resume"`; `NET-WIRE-001`/`NET-WIRE-002` → `"net-wire"`. Drop
`target_owner`/`target_observation` from all nine — those fields describe a still-pending
change, and the change has now landed.

- [ ] **Step 2: Update the checked-in digest**

```bash
uv run python tools/check_case_digest.py --update
```

- [ ] **Step 3: Write the parity test (RED first)**

```python
# tests/parity/test_acquisition_parity.py
"""Parity contract (D13): PackageAcquisitionRunner mirrors LegacyAcquisitionRunner's
process/raw contexts (tests/characterization/test_acquisition_matrix.py), driving
scoutmb.features.acquisition.service.AcquisitionService through the SAME strict fakes instead of
scout_schedule_cli.process_scout directly. Both runners are measured against the same
hand-computed AcquisitionCase.expected_legacy; neither is the other's oracle.

form/identity/asset contexts are skipped here -- they characterize scout_schedule_cli's own
module-level functions and AcquisitionService does not re-expose that surface; the process/raw
contexts are where the two implementations actually diverge and where this parity test earns
its keep. RetryPolicy is constructed with a very high breaker_threshold here specifically so
this per-scout test never trips it -- the breaker's cross-scout behavior is Task B5.5's test's
job, not this one's.
"""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from tests.characterization.test_acquisition_matrix import _normalize_raw_names, _project
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import (
    ACQUISITION_CASES,
    AcquisitionCase,
    AcquisitionObservation,
)
from tests.matrix.pytest_support import execution_params


class _RecordingSleeper:
    """Delegates to FakeClock so the package path's request-delay/backoff waits are recorded
    exactly like the legacy path's page.wait_for_timeout calls -- same clock, same assertions."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock

    async def sleep(self, seconds: float) -> None:
        self._clock.record(round(seconds * 1000))

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


class PackageAcquisitionRunner:
    """Runner[AcquisitionCase, AcquisitionObservation] over
    scoutmb.features.acquisition.service.AcquisitionService, driven through the identical
    StrictFakeBrowser/StrictScript/FakeClock LegacyAcquisitionRunner uses."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: AcquisitionCase, *, root: Path) -> AcquisitionObservation:
        if self.context_id not in {"process", "raw"}:
            pytest.skip(f"{self.context_id} exercises legacy-only surface (form/identity/asset)")

        clock = FakeClock()
        script = StrictScript(case.script)
        browser = StrictFakeBrowser(script, clock)
        gateway = PlaywrightScoutingEventGateway(
            browser,  # type: ignore[arg-type] - StrictFakeBrowser duck-types Browser
            allow_dead_assets=case.allow_dead_assets,
        )
        retry_policy = RetryPolicy(
            sleeper=_RecordingSleeper(clock), jitter=_ZeroJitter(), breaker_threshold=99
        )
        service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())

        result = asyncio.run(
            service.process(
                scout=ScoutInput(name=case.scout_name, url=case.qr_url),
                config=AcquisitionConfig(
                    timeout_seconds=case.timeout_seconds,
                    request_delay_ms=case.request_delay_ms,
                ),
                raw_dir=root / "raw",
                run_identity=RunIdentity(),
            )
        )
        script.assert_consumed()

        if self.context_id == "raw":
            return AcquisitionObservation(
                result=_project(result),
                relative_files=_normalize_raw_names(root),
                closed=browser.contexts[0].closed,
            )
        return AcquisitionObservation(
            result=_project(result),
            calls=tuple(script.calls),
            waits_ms=clock.waits_ms,
            closed=browser.contexts[0].closed,
        )


@pytest.mark.parametrize(("case", "context_id"), execution_params(ACQUISITION_CASES))
def test_package_runner_matches_expected_legacy(
    case: AcquisitionCase, context_id: str, tmp_path: Path
) -> None:
    if context_id not in {"process", "raw"}:
        pytest.skip(f"{context_id} has no package-side equivalent yet")

    runner = PackageAcquisitionRunner(context_id)
    observed = runner.run(case, root=tmp_path)

    expected = case.expected_legacy
    assert expected is not None
    if context_id == "process":
        expected = dataclasses.replace(expected, calls=tuple(req for req, _ in case.script))
    assert observed == expected
```

- [ ] **Step 4: Implement `AcquisitionService`**

```python
# src/scoutmb/features/acquisition/service.py
"""Orchestrates ONE scout's acquisition: opens a gateway session, fetches the schedule, dedupes
classes, fetches+validates each class's requirements with per-request retry, and returns a
ScoutResult. Preserves DOM name discovery, the full raw envelopes, the requirement-status check,
and HTML-cleaned descriptions -- all of which process_scout's current body does and which an
earlier draft of this service silently dropped.

Every raw/ write goes through the injected ArtifactSink (self.sink.publish_text), never
Path.write_text() directly -- matching exactly how features/reporting/service.py's
ReportingService routes every content write through its own injected sink while still calling
.mkdir(parents=True, exist_ok=True) itself (directory creation is orchestration; writing content
is the adapter's job).

Does NOT own the circuit breaker's check_closed()/record_failure()/record_success() calls, and
does NOT touch the checkpoint store -- both are batch-level decisions (features/acquisition/
batch.py, Task B5.5) that only make sense with visibility across an entire run's scouts, not one
scout in isolation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scoutmb.adapters.scoutevent.schema import ScoutingEventSchemaDrift, validate_requirement_row
from scoutmb.core.identity import AttendeeId, RunIdentity, attendee_filename_stem, safe_slug
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutInput, ScoutResult
from scoutmb.core.output_schemas import json_for_html
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.ports.artifact_sink import ArtifactSink
from scoutmb.ports.scoutevent import ScoutingEventGateway


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _days_from_class_name(class_name: str) -> str:
    if " - " in class_name:
        return class_name.split(" - ", 1)[0].strip()
    return ""


def _json_dump(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    timeout_seconds: int
    request_delay_ms: int


@dataclass(frozen=True, slots=True)
class AcquisitionService:
    gateway: ScoutingEventGateway
    retry_policy: RetryPolicy
    sink: ArtifactSink

    async def process(
        self,
        *,
        scout: ScoutInput,
        config: AcquisitionConfig,
        raw_dir: Path,
        run_identity: RunIdentity,
    ) -> ScoutResult:
        name = scout.name or "Unknown Scout"
        attendee_id = ""
        classes: list[ClassRecord] = []
        requirements: list[RequirementRecord] = []
        errors: list[str] = []

        try:
            async with self.gateway.open_session() as session:
                schedule = await session.fetch_schedule(
                    scout.url, config.timeout_seconds, scout.name
                )
                attendee_id = schedule.attendee_id
                if not attendee_id:
                    raise RuntimeError("The schedule request did not contain attendeeID")
                name = schedule.display_name

                raw_dir.mkdir(parents=True, exist_ok=True)
                output_id = run_identity.output_id(AttendeeId.parse(attendee_id, name))
                slug = attendee_filename_stem(name, output_id)
                self.sink.publish_text(
                    raw_dir / f"{slug}-schedule.json", _json_dump(schedule.payload), encoding="utf-8"
                )

                if int((schedule.payload.get("status") or {}).get("status", 0)) != 1:
                    raise RuntimeError(
                        f"Schedule API returned failure: {schedule.payload.get('status')}"
                    )

                schedule_rows = schedule.payload.get("data") or []
                deduped: dict[str, dict[str, Any]] = {}
                order: list[str] = []
                for item in schedule_rows:
                    key = str(item.get("classP4ID") or "")
                    if not key:
                        key = f"__no_id_{len(order)}"
                        deduped[key] = dict(item)
                        order.append(key)
                    elif key not in deduped:
                        deduped[key] = dict(item)
                        order.append(key)
                    elif _truthy(item.get("CLASS_COMPLETED")) and not _truthy(
                        deduped[key].get("CLASS_COMPLETED")
                    ):
                        deduped[key] = dict(item)

                for item in (deduped[key] for key in order):
                    raw_class_name = str(item.get("CLASS_NAME") or "")
                    class_record = ClassRecord(
                        scout_name=name,
                        attendee_id=attendee_id,
                        class_number=str(item.get("CLASS_NBR") or ""),
                        class_p4_id=str(item.get("classP4ID") or ""),
                        class_name=str(item.get("CLASS_NAME_ONLY") or ""),
                        days=_days_from_class_name(raw_class_name),
                        period_name=str(item.get("PERIOD_NAME") or ""),
                        start_time=str(item.get("CLASS_STIME") or ""),
                        start_time_24h=str(item.get("STIME") or ""),
                        location=str(item.get("LOCATION_ROOM_NAME") or ""),
                        has_requirements=_truthy(item.get("HAS_REQ")),
                        class_completed=_truthy(item.get("CLASS_COMPLETED")),
                        raw_class_name=raw_class_name,
                    )
                    classes.append(class_record)

                    # ACQ-HASREQ-002: skip the requirement fetch entirely when HAS_REQ='0',
                    # instead of issuing it and relying on the response being empty.
                    if not class_record.class_p4_id or not class_record.has_requirements:
                        continue

                    requirement_payload: dict[str, Any] | None = None
                    last_error: Exception | None = None
                    for attempt in range(1, 4):
                        try:
                            requirement_payload = await session.fetch_requirements(
                                attendee_id, class_record.class_p4_id
                            )
                            break
                        except Exception as exc:
                            last_error = exc
                            await self.retry_policy.wait_after_failure(attempt)

                    if requirement_payload is None:
                        errors.append(
                            f"{class_record.class_name}: requirement request failed: {last_error}"
                        )
                        continue

                    self.sink.publish_text(
                        raw_dir
                        / f"{slug}-{safe_slug(class_record.class_number or class_record.class_p4_id)}-requirements.json",
                        _json_dump(requirement_payload),
                        encoding="utf-8",
                    )

                    if int((requirement_payload.get("status") or {}).get("status", 0)) != 1:
                        errors.append(
                            f"{class_record.class_name}: requirement API returned failure: "
                            f"{requirement_payload.get('status')}"
                        )
                        continue

                    for row in requirement_payload.get("data") or []:
                        try:
                            validated = validate_requirement_row(dict(row))
                        except ScoutingEventSchemaDrift as exc:
                            errors.append(f"{class_record.class_name}: {exc}")
                            continue
                        requirements.append(
                            RequirementRecord(
                                scout_name=name,
                                attendee_id=attendee_id,
                                class_number=class_record.class_number,
                                class_p4_id=class_record.class_p4_id,
                                merit_badge_name=validated["merit_badge_name"],
                                requirement_id=validated["requirement_id"],
                                requirement_type_id=validated["requirement_type_id"],
                                requirement_number=validated["requirement_number"],
                                description=validated["description"],
                                completed_requirement=validated["completed_requirement"],
                                completed_class=validated["completed_class"],
                                requirement_on_event=validated["requirement_on_event"],
                                present_days=validated["present_days"],
                            )
                        )

                    if config.request_delay_ms > 0:
                        await self.retry_policy.sleeper.sleep(config.request_delay_ms / 1000)

        except Exception as exc:
            errors.append(str(exc))

        return ScoutResult(
            name=name,
            qr_url=scout.url,
            attendee_id=attendee_id,
            classes=tuple(classes),
            requirements=tuple(requirements),
            errors=tuple(errors),
        )
```

> `json_for_html` is imported but unused above — remove it before landing; it was pulled in by
> habit from a neighboring module and does not belong here. Flagged explicitly rather than left
> in, since an unused import is exactly the kind of small thing this review pass exists to catch.

- [ ] **Step 5: Write the resource-closing integration test**

```python
# tests/integration/test_acquisition_lifecycle.py
"""Every attendee-session resource closes, including when the gateway raises before the
session context manager's body completes."""

from __future__ import annotations

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
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


async def test_context_closes_even_when_schedule_fetch_raises(tmp_path) -> None:
    clock = FakeClock()
    script = StrictScript(())  # nothing scripted -> the gateway's first call raises immediately
    browser = StrictFakeBrowser(script, clock)
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())

    result = await service.process(
        scout=ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=X"),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
        run_identity=RunIdentity(),
    )

    assert result.errors  # the unscripted call failed and was recorded, not raised out
    assert browser.contexts, "a context must have been opened to fail inside"
    assert browser.contexts[0].closed is True
```

Note: `AcquisitionService.process()` no longer raises `BreakerOpen` (that decision moved to
Task B5.5's batch loop), so the earlier draft's "open breaker raises before any context is
opened" test moves there too, against `run_batch()` instead.

- [ ] **Step 6: Run everything and commit**

```bash
uv run pytest tests/parity/test_acquisition_parity.py tests/integration/test_acquisition_lifecycle.py tests/characterization/test_acquisition_matrix.py tests/matrix tests/unit/acquisition -q
```

```bash
git add src/scoutmb/features/acquisition/service.py tests/parity/test_acquisition_parity.py tests/integration/test_acquisition_lifecycle.py tests/matrix/cases/acquisition_cases.py tests/baselines/preserve_cases.json
git commit -m "feat(acquisition): AcquisitionService handles one scout, routes writes through ArtifactSink, lands ACQ-HASREQ-002"
```

---

## Task B5.5: `features/acquisition/batch.py` — run-scoped composition (breaker + checkpoint + `RunIdentity` hydration)

**Goal:** `run_batch()` composes one `RetryPolicy` (shared across every scout, so the breaker's
cross-scout premise is actually satisfied), the `CheckpointStore` (skip completed scouts on
resume, persist the attendee→output-UUID map after every scout), and `RunIdentity`
hydration/snapshot into a single function that drives a whole run's scouts through
`AcquisitionService`. This is the function `scout_schedule_cli.async_main` (sub-plan 4's Task
B10.2) and `interfaces/cli/schedule.py` (sub-plan 3's `troop349-schedule`) both call — the actual
orchestration logic lives in the package, not in a flat module either of those callers'
successors need to survive.

**Files:**
- Create: `src/scoutmb/features/acquisition/batch.py`
- Modify: `src/scoutmb/core/identity.py` (`RunIdentity.snapshot()`/`.hydrate()`)
- Test: `tests/integration/test_acquisition_batch.py`

**Acceptance Criteria:**
- [ ] A single `RetryPolicy` instance is constructed once by `run_batch()`'s caller and shared
      across every scout — the breaker's consecutive-failure count spans the whole run, not one
      scout
- [ ] `run_batch()` checks `retry_policy.check_closed()` before starting each scout (raising
      `BreakerOpen` there, not inside `AcquisitionService.process()`) and calls
      `record_failure()`/`record_success()` based on whether that scout's `ScoutResult.errors`
      is empty — one recording per scout, not one per retry attempt
- [ ] A scout whose QR URL is already in the checkpoint's `completed_urls` is skipped entirely —
      `AcquisitionService.process()` is never called for it
- [ ] After each scout, the checkpoint is saved with that scout's URL added to `completed_urls`
      and `run_identity.snapshot()` as `output_ids` — a resumed run reuses the same output UUIDs
- [ ] A fresh `RunIdentity` hydrated from a prior checkpoint's `output_ids` returns the same
      `output_id` for an attendee ID it already had a UUID for, proven by reconstructing a new
      `RunIdentity` from a saved snapshot (simulating a process restart) — not merely asserting
      against the same in-memory instance

**Verify:** `uv run pytest tests/integration/test_acquisition_batch.py tests/unit/test_identity.py -q` → PASS

**Recovery:** Leave `run_batch()` unreferenced; `scout_schedule_cli.async_main`'s inline loop
stays the live path until sub-plan 4's Task B10.2 wires this in.

**Steps:**

- [ ] **Step 1: Add hydrate/snapshot to `RunIdentity`**

```python
# src/scoutmb/core/identity.py -- add two methods to the existing RunIdentity class
    def snapshot(self) -> Mapping[str, str]:
        """A read-only view of the current attendee-id -> output-id map, for persisting into a
        checkpoint. Not a live view -- callers that need to observe later output_id() calls must
        re-snapshot."""
        return MappingProxyType(dict(self._by_attendee))

    def hydrate(self, existing: Mapping[str, str]) -> None:
        """Seed this instance's map from a prior run's snapshot (e.g. a loaded checkpoint), so
        an attendee this run already resolved on a previous process gets the SAME output_id
        again rather than a fresh one. Only call this before any output_id() calls on this
        instance -- hydrating after would not retroactively change UUIDs already handed out."""
        self._by_attendee.update(existing)
```

```python
# src/scoutmb/core/identity.py -- add to the existing imports at the top
from collections.abc import Mapping
from types import MappingProxyType
```

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/test_acquisition_batch.py
"""ACQ-BREAKER/ACQ-RESUME end to end: a shared RetryPolicy sees failures across scouts (not
reset per scout), a checkpoint skips completed scouts and persists output-UUIDs across a
simulated process restart."""

from __future__ import annotations

import pytest

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput
from scoutmb.features.acquisition.batch import run_batch
from scoutmb.features.acquisition.retry import BreakerOpen, RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.ports.checkpoint_store import Checkpoint
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


def _service(browser: StrictFakeBrowser, retry_policy: RetryPolicy) -> AcquisitionService:
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    return AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())


async def test_breaker_state_is_shared_across_scouts(tmp_path) -> None:
    """Two scouts, both scripted to fail their schedule fetch (nothing scripted -> the gateway's
    first call raises). A threshold-2 breaker must open on the SECOND scout's failure, proving
    the RetryPolicy instance -- not a fresh one per scout -- is what run_batch threads through."""
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=2)
    service = _service(browser, retry_policy)
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    run_identity = RunIdentity()

    scouts = [
        ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
        ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
        ScoutInput(name="Casey", url="https://scoutingevent.com/mobile/checkin?t=C"),
    ]

    with pytest.raises(BreakerOpen):
        await run_batch(
            scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            run_identity=run_identity,
            config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
            raw_dir=tmp_path / "raw",
        )
    # The third scout ("Casey") must never have been attempted -- the breaker opened after the
    # second scout's failure, before a third BrowserContext could be opened.
    assert len(browser.contexts) == 2


async def test_completed_scout_is_skipped_on_resume(tmp_path) -> None:
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint_store.save(
        Checkpoint(
            version=1,
            completed_urls=("https://scoutingevent.com/mobile/checkin?t=A",),
            output_ids={},
        )
    )
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # nothing scripted -- must never be called
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = _service(browser, retry_policy)

    await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )
    assert browser.contexts == []  # never attempted -- the checkpoint already had it


async def test_output_uuid_survives_a_simulated_process_restart(tmp_path) -> None:
    """Save a checkpoint carrying a prior output_id for an attendee, then construct a BRAND NEW
    RunIdentity (simulating a fresh process) and hydrate it from that checkpoint -- the same
    attendee must resolve to the SAME output_id, not a freshly-minted one."""
    from scoutmb.core.identity import AttendeeId

    prior_output_id = "11111111-1111-4111-8111-111111111111"
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint_store.save(
        Checkpoint(version=1, completed_urls=(), output_ids={"A1": prior_output_id})
    )

    fresh_run_identity = RunIdentity()
    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    fresh_run_identity.hydrate(checkpoint.output_ids)

    assert fresh_run_identity.output_id(AttendeeId.parse("A1")) == prior_output_id
```

Run: `uv run pytest tests/integration/test_acquisition_batch.py -v` → FAIL (module doesn't exist)

- [ ] **Step 3: Implement `run_batch`**

```python
# src/scoutmb/features/acquisition/batch.py
"""Run-scoped acquisition composition (D22, ACQ-BREAKER, ACQ-RESUME). Owns the ONE RetryPolicy
shared across every scout in the run (so its breaker sees cross-scout failures, matching
ACQ-BREAKER's own rationale), the checkpoint store (skip completed scouts, persist output-UUIDs),
and RunIdentity hydration. AcquisitionService.process() handles one scout in isolation and knows
nothing about any of this -- see that module's docstring for why."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput, ScoutResult
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.ports.checkpoint_store import CHECKPOINT_VERSION, Checkpoint, CheckpointStore


async def run_batch(
    scouts: Sequence[ScoutInput],
    *,
    service: AcquisitionService,
    retry_policy: RetryPolicy,
    checkpoint_store: CheckpointStore,
    run_identity: RunIdentity,
    config: AcquisitionConfig,
    raw_dir: Path,
) -> list[ScoutResult]:
    checkpoint = checkpoint_store.load()
    if checkpoint is not None:
        run_identity.hydrate(checkpoint.output_ids)
    completed_urls = set(checkpoint.completed_urls) if checkpoint is not None else set()

    results: list[ScoutResult] = []
    for scout in scouts:
        if scout.url in completed_urls:
            continue

        retry_policy.check_closed()  # raises BreakerOpen before opening a session for this scout
        result = await service.process(
            scout=scout, config=config, raw_dir=raw_dir, run_identity=run_identity
        )
        results.append(result)

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

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/integration/test_acquisition_batch.py tests/unit/test_identity.py -q
```

```bash
git add src/scoutmb/features/acquisition/batch.py src/scoutmb/core/identity.py tests/integration/test_acquisition_batch.py
git commit -m "feat(acquisition): run_batch composes shared RetryPolicy + checkpoint + RunIdentity hydration"
```

---

## Sub-plan gate (feeds Gate 2)

- Both runners (legacy, package) green for every `ACQ-*` execution key.
- `ACQ-BREAKER-001/002/003`, `ACQ-RESUME-001/002/003/004`, `NET-WIRE-001/002` all carry
  `contexts` and a passing runner — no longer `contexts=()` placeholders.
- `ACQ-REQ-004` and `ACQ-HASREQ-002` expectations updated in `tests/matrix/cases/acquisition_cases.py`,
  digest bumped (`uv run python tools/check_case_digest.py --update`) in the same commit as each change.
- Egress check proven for both the schedule and requirement gateways (unit tests in B4.1/B4.2),
  and the full existing `ACQ-*` suite stays green under the opt-in fixture.
- DOM name discovery, full raw envelopes, requirement-status checks, and HTML-cleaned
  descriptions are all preserved through the gateway/service redesign — not merely asserted, each
  has its own test.
- The circuit breaker's state is shared across an entire run's scouts (Task B5.5), not rebuilt
  per scout; the checkpoint store is actually wired into a batch loop that skips completed
  scouts and persists `RunIdentity`'s map across a simulated process restart.
- Every browser context/session closes on the success, error, and breaker-open paths
  (`tests/integration/test_acquisition_lifecycle.py`, `test_acquisition_batch.py`).
- `AcquisitionService` writes every raw/ file through `ArtifactSink`, never `Path.write_text()`.
- `CorruptCheckpoint` subclasses `ScoutmbError`; `Checkpoint.output_ids` is a genuine
  `MappingProxyType`, not a typed-but-mutable `dict`.
- `process_scout`'s external signature and every existing caller unchanged.
- `uv run pytest -q` green with no regressions in `tests/characterization/`, `tests/parity/`, or
  `tests/architecture/`.

**NO-GO:** Disable `AcquisitionService`/`run_batch` at whatever composition point sub-plan 4's
Task B10.2 wires them into; restore `process_scout`'s inline loop; keep the gateway/schema/retry/
checkpoint units merged but unused; return the specific failing row to its task.
