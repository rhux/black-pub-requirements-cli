"""A guarded Playwright browser context that blocks non-loopback network egress (Task 19).

``scout_schedule_cli`` drives a REAL Chromium subprocess, which pytest-socket cannot see (it
only patches sockets inside this Python process -- see ``src/scoutmb/network_policy.py``'s
docstring). This harness is the browser-lane equivalent of that same defense-in-depth idea:
every request/navigation/redirect/frame/popup/worker/WebSocket/download a guarded context's
pages make is checked against ``LOOPBACK_HOSTS`` before it can leave the sandbox.

Three enforcement paths, because Playwright does not offer one mechanism that covers everything:

* Ordinary requests (navigation, in-page fetch/XHR, frame subresources, and popups, since a
  context-level route also covers pages opened later in that same context) go through
  ``context.route("**/*", ...)``, which can genuinely abort the request before it reaches the
  network.
* Navigation redirects need special handling within that same route handler: verified
  empirically against this Playwright/Chromium build, ``context.route()``'s handler is never
  re-invoked for the redirected hop of a main-frame navigation -- Chromium's Fetch-domain
  request interception treats that hop as part of the same network-service-level redirect, not
  a fresh renderer-issued request, so it never reaches Playwright's routing layer a second time
  (confirmed by instrumenting every Playwright/CDP event: ``page.on("request")`` sees the
  redirected URL, but the registered route handler never fires for it, with or without a
  detector attached). The fix: for a navigation request, fetch the response ourselves with
  ``route.fetch(max_redirects=0)`` -- so nothing is auto-followed -- inspect its ``Location``
  header BEFORE the browser ever sees it, and abort in place (``route.fulfill`` with a 403) if
  that target is non-loopback. Nothing reaches the network for that hop. A loopback ``Location``
  is relayed back to the browser as a genuine redirect response via ``route.fulfill(response=...)``,
  which makes the browser issue a brand-new top-level navigation request for it -- and that
  fresh request re-enters this same route handler normally.
* A dedicated Web Worker's own runtime network calls (e.g. a `fetch()` issued from inside the
  worker script) ARE interceptable through the same context-level ``route()`` -- verified
  empirically against this Playwright/Chromium build: a worker's internal `fetch()` to a
  non-loopback host is seen and aborted by the same route handler that catches page-level
  fetches, with no extra wiring required. The ``page.on("worker", ...)`` listener below is
  NOT what catches that traffic; it fires exactly once, at worker creation, with the worker's
  own *script* URL (loopback in every case here, since the script is always same-origin) --
  it exists only to record that a worker was spawned, not to observe anything the worker's
  own code subsequently fetches.
* WebSocket connections and triggered downloads genuinely are NOT interceptable through
  ``route()`` in Playwright, so those are caught with ``page.on("websocket", ...)`` /
  ``page.on("download", ...)`` listeners instead. Playwright dispatches those (and the
  worker-creation event above) as fire-and-forget sync callbacks -- an exception raised
  inside one is logged, not propagated to the awaiting caller -- so
  ``GuardedContext.violations`` is the durable, awaitable-safe record a test reads after the
  action, in addition to ``assert_loopback`` raising on the spot wherever a caller can
  actually observe it (the route handler, and direct unit tests of ``assert_loopback``
  itself).

The blocked-request message never carries more than the scheme/host: never a path, query
string, request body, or header, even though every URL used against this harness in tests is
synthetic, not private corpus data -- the bound is honored unconditionally.
"""

from __future__ import annotations

import contextlib
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urljoin, urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.async_api import BrowserContext, Download, Page

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class ExternalBrowserRequest(Exception):
    """A guarded context observed a request/navigation/connection to a non-loopback host."""


def assert_loopback(url: str) -> None:
    host = urlsplit(url).hostname
    if host not in LOOPBACK_HOSTS:
        raise ExternalBrowserRequest(f"external browser request blocked: {host or '<none>'}")


@dataclass
class GuardedContext:
    """Owns the violation log for one guarded ``BrowserContext``."""

    context: BrowserContext
    violations: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)

    def _record(self, url: str) -> None:
        try:
            assert_loopback(url)
        except ExternalBrowserRequest as exc:
            self.violations.append(str(exc))

    def assert_clean(self) -> None:
        if self.violations:
            raise ExternalBrowserRequest("; ".join(self.violations))


async def install_egress_guard(context: BrowserContext) -> GuardedContext:
    """Install the guard on ``context`` BEFORE the first page is created.

    Covers, per the member list this harness backs: navigation, redirects (handled specially --
    see the module docstring -- because Chromium never re-invokes ``route()`` for a
    navigation's redirected hop), frames (iframe subresources route through the same context),
    popups (a context-level route also applies to pages opened later in that context), in-page
    fetch/XHR, and -- via the ``page.on`` listeners below, since routing does not reach them --
    dedicated Worker network access, WebSocket connection attempts, and triggered downloads.
    """
    guard = GuardedContext(context)

    async def _route_handler(route: object) -> None:
        request = route.request  # type: ignore[attr-defined]
        host = urlsplit(request.url).hostname
        if host not in LOOPBACK_HOSTS:
            guard.violations.append(f"external browser request blocked: {host or '<none>'}")
            await route.abort()  # type: ignore[attr-defined]
            return
        guard.allowed.append(host)
        if not request.is_navigation_request():
            await route.continue_()  # type: ignore[attr-defined]
            return
        # Navigation redirects: fetch the response ourselves without following any redirect,
        # so we can inspect its Location header before the browser ever acts on it. See the
        # module docstring for why route() alone cannot catch this hop.
        try:
            response = await route.fetch(max_redirects=0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a failed manual fetch is fail-closed, not a pass-through
            await route.abort()  # type: ignore[attr-defined]
            return
        location = response.headers.get("location")
        if response.status in (301, 302, 303, 307, 308) and location:
            target_host = urlsplit(urljoin(request.url, location)).hostname
            if target_host not in LOOPBACK_HOSTS:
                guard.violations.append(
                    f"external browser request blocked: {target_host or '<none>'}"
                )
                await route.fulfill(status=403, body=b"blocked by egress guard")  # type: ignore[attr-defined]
                return
        await route.fulfill(response=response)  # type: ignore[attr-defined]

    await context.route("**/*", _route_handler)

    def _guard_page(page: Page) -> None:
        page.on("worker", lambda worker: guard._record(worker.url))
        page.on("websocket", lambda ws: guard._record(ws.url))
        page.on("download", lambda download: guard._record(_download_url(download)))

    context.on("page", _guard_page)
    for page in context.pages:
        _guard_page(page)

    return guard


def _download_url(download: Download) -> str:
    return download.url


# --------------------------------------------------------------------------------------------
# A tiny, dependency-free, loopback-only fake service for BROWSER-LOCAL/BROWSER-EGRESS. Every
# route is deterministic. It never listens on anything but 127.0.0.1, and the OS assigns the
# port (bind to port 0) so parallel test runs never collide.
# --------------------------------------------------------------------------------------------
_SCHEDULE_PAYLOAD = {
    "status": {"status": 1},
    "data": [
        {
            "classP4ID": "2000001",
            "CLASS_NAME": "MoTuWeTh - Chess - 26MB1 (Pavilion)",
            "CLASS_NAME_ONLY": "Chess",
            "CLASS_NBR": "26MB1",
            "PERIOD_NAME": "A Block",
            "CLASS_STIME": "09:00 AM",
            "STIME": "09:00:00",
            "LOCATION_ROOM_NAME": "Pavilion",
            "HAS_REQ": "1",
            "CLASS_COMPLETED": "0",
        }
    ],
}
_REQUIREMENT_PAYLOAD = {
    "status": {"status": 1},
    "data": [
        {
            "MDM_LKP_BADGE_REQ_ID": "r1",
            "MDM_LKP_BADGE_REQ_TYPE_ID": "1",
            "MERIT_BADGE_NAME": "Chess",
            "REQ_NBR": "1",
            "REQ_NBR_WEB_DISPLAY": "#1",
            "REQ_DESCR": "Discuss the history of chess.",
            "COMPLETED_REQ_FLAG": "0",
            "COMPLETED_CLASS_FLAG": "0",
            "REQ_ON_EVENT": "1",
            "PRESENT_DAYS": "MoTuWeTh",
        }
    ],
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        return  # keep test output quiet; nothing here carries private data anyway

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query(self) -> dict[str, str]:
        parsed = urlsplit(self.path)
        return {k: v[-1] for k, v in parse_qs(parsed.query).items()}

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        path = urlsplit(self.path).path
        query = self._query()
        if path == "/":
            self._send_html("<html><body><h1>fake scoutingevent</h1></body></html>")
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", query.get("to", "/"))
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/frame":
            target = query.get("to", "/")
            self._send_html(f'<html><body><iframe src="{target}"></iframe></body></html>')
        elif path == "/popup":
            target = query.get("to", "/")
            self._send_html(
                f'<html><body><script>window.open("{target}", "_blank")</script></body></html>'
            )
        elif path == "/worker-script":
            target = query.get("to", "/")
            self._send_response_js(f'fetch("{target}").catch(() => {{}});')
        elif path == "/worker":
            target = query.get("to", "/")
            self._send_html(
                "<html><body><script>"
                f'new Worker("/worker-script?to={target}");'
                "</script></body></html>"
            )
        elif path == "/websocket":
            target = query.get("to", "")
            self._send_html(
                f'<html><body><script>new WebSocket("{target}");</script></body></html>'
            )
        else:
            self._send_html("<html><body>not found</body></html>", status=404)

    def _send_response_js(self, script: str) -> None:
        body = script.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib method name
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = {k: v[-1] for k, v in parse_qs(raw).items()}
        if path == "/mobile/inc/ajax_mobile.php":
            if str(form.get("getUnitClass", "")).lower() == "true":
                self._send_json(_SCHEDULE_PAYLOAD)
            elif "classP4ID" in form:
                self._send_json(_REQUIREMENT_PAYLOAD)
            else:
                self._send_json({"status": {"status": 0}, "data": []})
        else:
            self._send_json({"status": {"status": 0}}, status=404)


@dataclass
class LoopbackFakeService:
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
def loopback_fake_service() -> Iterator[LoopbackFakeService]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service = LoopbackFakeService(server, thread)
    try:
        yield service
    finally:
        service.stop()
