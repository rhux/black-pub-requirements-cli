"""Real-Playwright execution of STATIC-UI (Task 21).

Drives the REAL, unmodified files under ``ui/static/`` (index.html, app.js, styles.css) in a
REAL Chromium browser (marked ``playwright``, deselected by default) against a small
loopback-only fake backend defined in this module. The fake backend answers exactly the
routes ``ui/static/app.js`` calls (``/api/status``, ``/api/scouts``, ``/api/runs``,
``/api/schedule-download``, its ``pause``/``resume`` siblings, ``/api/operations/{id}/events``
SSE, and ``/api/runs/{id}/open-report``) with deterministic, scripted payloads -- the real
frontend JS is exercised end-to-end, only the server side is synthetic. Navigation goes
through Task 19's guarded browser context (``tests.harnesses.browser``), so any attempt by the
page to reach a non-loopback host would show up as a guard violation.

Structure note (matrix-case vs. plain functions): this member set is exactly three broad,
sequential, stateful end-to-end browser scenarios (successful run, progress/pause/resume, error
run), not a combinatorial set of small independent data points. The matrix-case machinery
(axis membership, ``min_focused_cases``, boundary bookkeeping) is built to keep many small,
independently-orderable cases honest against a declared input space -- it buys little here,
where each "case" is really one long, carefully-sequenced browser interaction whose ordering
*is* the test. Three well-documented ``test_*`` functions, each covering one member end to end,
is the better fit for this specific domain; the docstrings above and on each test carry the
same rationale/evidence a matrix case's metadata would.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.async_api import Browser, BrowserContext, ConsoleMessage, Page, async_playwright
from tests.harnesses.browser import GuardedContext, install_egress_guard

pytestmark = pytest.mark.playwright

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = _REPO_ROOT / "ui" / "static"

_STATIC_FILES: dict[str, tuple[bytes, str]] = {
    "/": ((_STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8"),
    "/index.html": ((_STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8"),
    "/app.js": ((_STATIC_DIR / "app.js").read_bytes(), "application/javascript"),
    "/styles.css": ((_STATIC_DIR / "styles.css").read_bytes(), "text/css"),
}


# --------------------------------------------------------------------------------------------
# Loopback-only fake backend: real ``ui/static`` files + scripted API/SSE responses.
# --------------------------------------------------------------------------------------------
@dataclass
class _SyncGates:
    """Lets a scenario's SSE generator (running in the ``/events`` request's own handler
    thread) block until the test's click on Pause/Resume actually reaches the fake server --
    the same ordering a real backend would observe."""

    pause_requested: threading.Event = field(default_factory=threading.Event)
    resume_requested: threading.Event = field(default_factory=threading.Event)


@dataclass
class ScenarioConfig:
    scouts_rows: list[dict[str, str]]
    sse_events: Callable[[_SyncGates], Iterator[dict[str, object]]]
    schedule_operation_id: str = "op-1"
    schedule_run_id: str = "RUN-1"


def _make_handler(config: ScenarioConfig, gates: _SyncGates) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
            return  # keep test output quiet

        def _send_json(self, payload: object, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, path: str) -> None:
            entry = _STATIC_FILES.get(path)
            if entry is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body, content_type = entry
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            for event in config.sse_events(gates):
                chunk = f"data: {json.dumps(event)}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            path = urlsplit(self.path).path
            if path in _STATIC_FILES:
                self._send_static(path)
            elif path == "/api/status":
                self._send_json(
                    {
                        "scouts_csv_exists": True,
                        "scouts_count": len(config.scouts_rows),
                        "scouts_mtime": "2026-07-23T12:00:00",
                    }
                )
            elif path == "/api/scouts":
                self._send_json(config.scouts_rows)
            elif path == "/api/runs":
                self._send_json([])
            elif path.startswith("/api/operations/") and path.endswith("/events"):
                self._stream_events()
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_POST(self) -> None:  # noqa: N802 - stdlib method name
            path = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            if length:
                self.rfile.read(length)  # drain any multipart/form body, unused here
            if path == "/api/schedule-download":
                self._send_json(
                    {
                        "operation_id": config.schedule_operation_id,
                        "run_id": config.schedule_run_id,
                    },
                    status=202,
                )
            elif path == "/api/schedule-download/pause":
                gates.pause_requested.set()
                self._send_json({"paused": True})
            elif path == "/api/schedule-download/resume":
                gates.resume_requested.set()
                self._send_json({"paused": False})
            elif path.startswith("/api/runs/") and path.endswith("/open-report"):
                self._send_json({"opened": True, "url": f"http://127.0.0.1{path}"})
            else:
                self._send_json({"detail": "not found"}, status=404)

    return Handler


@dataclass
class ScenarioServer:
    server: ThreadingHTTPServer
    thread: threading.Thread

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


@contextlib.contextmanager
def scenario_server(config: ScenarioConfig) -> Iterator[ScenarioServer]:
    gates = _SyncGates()
    handler_cls = _make_handler(config, gates)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service = ScenarioServer(server, thread)
    try:
        yield service
    finally:
        service.stop()


# --------------------------------------------------------------------------------------------
# Browser plumbing (Task 19's guarded context). Function-scoped, exactly like
# test_browser_matrix.py's own ``browser`` fixture: this repo's pytest-asyncio config uses a
# fresh event loop per test function (no ``asyncio_default_fixture_loop_scope`` override), and
# Playwright's async objects are bound to the loop that created them -- a module- or
# session-scoped async browser fixture would hand a later test's differently-scoped fixtures
# (and their own fresh loop) a Browser created on a now-foreign loop, which hangs (verified
# empirically: swapping this to ``scope="module"`` reproduces an indefinite hang inside
# ``chromium.launch()``'s subprocess-management asyncio machinery, confirmed via a SIGABRT
# faulthandler dump landing in ``asyncio.unix_events._do_waitpid`` on a foreign loop).
@pytest.fixture
async def browser() -> AsyncIterator[Browser]:
    async with async_playwright() as playwright:
        chromium = await playwright.chromium.launch(headless=True)
        try:
            yield chromium
        finally:
            await chromium.close()


@pytest.fixture
async def guarded(browser: Browser) -> AsyncIterator[tuple[BrowserContext, GuardedContext]]:
    context = await browser.new_context(ignore_https_errors=True)
    guard = await install_egress_guard(context)
    try:
        yield context, guard
    finally:
        await context.close()


def _install_console_capture(page: Page) -> list[str]:
    messages: list[str] = []
    page.on(
        "console",
        lambda message: messages.append(message.text)
        if isinstance(message, ConsoleMessage) and message.type == "error"
        else None,
    )
    page.on("pageerror", lambda exc: messages.append(str(exc)))
    return messages


async def _wait_for_text(page: Page, selector: str, substring: str, timeout: int = 8000) -> None:
    await page.wait_for_function(
        "(args) => { const [sel, text] = args; const el = document.querySelector(sel); "
        "return !!el && el.textContent.includes(text); }",
        arg=[selector, substring],
        timeout=timeout,
    )


def _status_cell_selector(index: int) -> str:
    return f"#scouts-table tbody tr[data-index='{index}'] .status-cell"


# --------------------------------------------------------------------------------------------
# STATIC-UI-001: successful terminal DOM.
# --------------------------------------------------------------------------------------------
async def test_success_terminal_dom(
    guarded: tuple[BrowserContext, GuardedContext],
) -> None:
    """One scout, one class run, no errors: assert the download completes, the scout row shows
    a success badge, the progress bar reaches 100%, controls are re-enabled, and no unexpected
    JS console errors were logged."""
    scouts_rows = [{"name": "Alice Scout", "registrant_type": "Scout"}]

    def events(gates: _SyncGates) -> Iterator[dict[str, object]]:
        del gates  # this scenario never pauses
        yield {"type": "batch_start", "total": 1}
        yield {"type": "scout_start", "index": 1, "total": 1}
        yield {
            "type": "scout_done",
            "index": 1,
            "total": 1,
            "classes": 3,
            "requirements": 10,
            "errors": 0,
        }
        yield {
            "type": "batch_done",
            "run_id": "RUN-1",
            "scouts_processed": 1,
            "scouts_with_errors": 0,
            "report_url": "/runs/RUN-1/report.html",
        }

    config = ScenarioConfig(scouts_rows=scouts_rows, sse_events=events)
    with scenario_server(config) as service:
        context, guard = guarded
        page = await context.new_page()
        console_errors = _install_console_capture(page)
        await page.goto(service.base_url + "/")
        await page.wait_for_selector("#scouts-panel:not([hidden])")

        await page.click("#download-btn")
        assert await page.is_disabled("#download-btn")
        assert await page.is_disabled("#reload-pdfs-btn")
        assert await page.is_visible("#pause-resume-btn")

        # Progress/completion badge: driven solely by the scout_done SSE frame, so this is
        # deterministic (no other writer touches this cell before the terminal reload below).
        await _wait_for_text(page, _status_cell_selector(0), "classes=3, requirements=10")
        badge_class = await page.get_attribute(f"{_status_cell_selector(0)} .badge", "class")
        assert badge_class is not None
        assert "success" in badge_class
        progress_width = await page.eval_on_selector(
            "#download-progress .progress-fill", "el => el.style.width"
        )
        assert progress_width == "100%"

        # Terminal marker: batch_done's fire-and-forget openReport() call is the very last DOM
        # mutation this run makes, so waiting for its toast text is the deterministic way to
        # know the whole scenario (batch_done -> refreshStatusAndRuns -> openReport) settled.
        await _wait_for_text(page, "#toast", "Opened in your browser.")

        assert not await page.is_disabled("#download-btn")
        assert not await page.is_disabled("#reload-pdfs-btn")
        assert not await page.is_disabled("#upload-submit")
        assert not await page.is_visible("#pause-resume-btn")
        assert (await page.text_content("#download-status")) == ""

        # Real (if easy to miss) app.js behavior: batch_done's own refreshStatusAndRuns() call
        # reloads /api/scouts and re-renders the whole table from scratch, which resets every
        # row's badge back to the initial "Not downloaded yet" pending state -- the per-scout
        # success badge asserted above is genuine but transient, not the final resting state.
        final_status_cell = await page.text_content(_status_cell_selector(0))
        assert final_status_cell is not None
        assert "Not downloaded yet" in final_status_cell

        toast_class = await page.get_attribute("#toast", "class")
        assert toast_class is not None
        assert "error" not in toast_class

        guard.assert_clean()
        assert console_errors == []


# --------------------------------------------------------------------------------------------
# STATIC-UI-002: progress, then paused/resumed.
# --------------------------------------------------------------------------------------------
async def test_progress_then_paused_resumed_dom(
    guarded: tuple[BrowserContext, GuardedContext],
) -> None:
    """Two scouts: the first completes (progress reaches 50%), the user pauses, the fake
    backend emits ``paused`` only after that request lands (mirroring "finish the current
    scout, then stop"), the user resumes, and the second scout completes the run."""
    scouts_rows = [
        {"name": "Alice Scout", "registrant_type": "Scout"},
        {"name": "Bob Scout", "registrant_type": "Scout"},
    ]

    def events(gates: _SyncGates) -> Iterator[dict[str, object]]:
        yield {"type": "batch_start", "total": 2}
        yield {"type": "scout_start", "index": 1, "total": 2}
        yield {
            "type": "scout_done",
            "index": 1,
            "total": 2,
            "classes": 2,
            "requirements": 5,
            "errors": 0,
        }
        gates.pause_requested.wait(timeout=5)
        yield {"type": "paused", "index": 2, "total": 2}
        gates.resume_requested.wait(timeout=5)
        yield {"type": "resumed"}
        yield {"type": "scout_start", "index": 2, "total": 2}
        yield {
            "type": "scout_done",
            "index": 2,
            "total": 2,
            "classes": 1,
            "requirements": 4,
            "errors": 0,
        }
        yield {
            "type": "batch_done",
            "run_id": "RUN-2",
            "scouts_processed": 2,
            "scouts_with_errors": 0,
            "report_url": "/runs/RUN-2/report.html",
        }

    config = ScenarioConfig(scouts_rows=scouts_rows, sse_events=events)
    with scenario_server(config) as service:
        context, guard = guarded
        page = await context.new_page()
        console_errors = _install_console_capture(page)
        await page.goto(service.base_url + "/")
        await page.wait_for_selector("#scouts-panel:not([hidden])")

        await page.click("#download-btn")

        # Progress: scout 1 finishes -> 50%.
        await _wait_for_text(page, _status_cell_selector(0), "classes=2, requirements=5")
        progress_after_first = await page.eval_on_selector(
            "#download-progress .progress-fill", "el => el.style.width"
        )
        assert progress_after_first == "50%"

        # Pause after the current scout: click, then wait for the button to flip to "Resume"
        # (set identically by both the click handler's own fetch response and the SSE "paused"
        # frame, so this is race-free -- unlike download-status below).
        assert await page.is_visible("#pause-resume-btn")
        await page.click("#pause-resume-btn")
        await page.wait_for_function(
            "() => document.getElementById('pause-resume-btn').dataset.paused === 'true'"
        )
        assert (await page.text_content("#pause-resume-btn")) == "Resume"
        # download-status is genuinely racy in real app.js: the click handler's own fetch
        # response sets "Pausing -- the current scout will finish..." while the SSE "paused"
        # frame (delivered over an independent connection) sets "Paused before scout 2/2...";
        # whichever resolves last in the browser's event loop wins, with no synchronization
        # between the two in the shipped code. Assert only that one of the two valid, real
        # strings is showing -- not which one -- to avoid pinning a timing-dependent outcome.
        download_status_while_paused = await page.text_content("#download-status")
        assert download_status_while_paused in {
            "Pausing — the current scout will finish, then downloading will stop.",
            "Paused before scout 2/2. Click Resume to continue.",
        }

        # Resume: run completes.
        await page.click("#pause-resume-btn")
        await _wait_for_text(page, "#toast", "Opened in your browser.")

        assert (await page.text_content("#pause-resume-btn")) == "Pause after current scout"
        assert not await page.is_visible("#pause-resume-btn")
        # Same real reset behavior as STATIC-UI-001: refreshStatusAndRuns() reloads the scouts
        # table after batch_done, so both rows are back to their pending badge, not the
        # per-scout results shown while the run was in progress.
        final_status = await page.text_content(_status_cell_selector(1))
        assert final_status is not None
        assert "Not downloaded yet" in final_status
        progress_final = await page.eval_on_selector(
            "#download-progress .progress-fill", "el => el.style.width"
        )
        assert progress_final == "100%"
        assert (await page.text_content("#download-status")) == ""
        assert not await page.is_disabled("#download-btn")

        guard.assert_clean()
        assert console_errors == []


# --------------------------------------------------------------------------------------------
# STATIC-UI-003: error terminal DOM.
# --------------------------------------------------------------------------------------------
async def test_error_terminal_dom(
    guarded: tuple[BrowserContext, GuardedContext],
) -> None:
    """The batch worker fails mid-run: assert the toast reports the failure text and is styled
    as an error, all controls are re-enabled (not left disabled/stuck), the pause/resume button
    is hidden again, and no unexpected JS console errors were logged."""
    scouts_rows = [{"name": "Casey Scout", "registrant_type": "Scout"}]

    def events(gates: _SyncGates) -> Iterator[dict[str, object]]:
        del gates  # this scenario never reaches pause
        yield {"type": "batch_start", "total": 1}
        yield {"type": "scout_start", "index": 1, "total": 1}
        yield {"type": "error", "message": "browser session could not be established"}

    config = ScenarioConfig(scouts_rows=scouts_rows, sse_events=events)
    with scenario_server(config) as service:
        context, guard = guarded
        page = await context.new_page()
        console_errors = _install_console_capture(page)
        await page.goto(service.base_url + "/")
        await page.wait_for_selector("#scouts-panel:not([hidden])")

        await page.click("#download-btn")
        await _wait_for_text(
            page, "#toast", "Download failed: browser session could not be established"
        )

        toast_class = await page.get_attribute("#toast", "class")
        assert toast_class is not None
        assert "error" in toast_class

        assert not await page.is_disabled("#download-btn")
        assert not await page.is_disabled("#reload-pdfs-btn")
        assert not await page.is_disabled("#upload-submit")
        assert not await page.is_visible("#pause-resume-btn")
        assert (await page.text_content("#download-status")) == ""

        guard.assert_clean()
        assert console_errors == []
