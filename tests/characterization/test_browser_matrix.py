"""Real-Playwright execution of BROWSER-LOCAL / BROWSER-EGRESS (Task 19).

Every test here drives a REAL Chromium browser (marked ``playwright``, deselected by
default -- see ``pyproject.toml``) against the loopback-only fake service in
``tests/harnesses/browser.loopback_fake_service``. BROWSER-EGRESS cases additionally attempt
one non-loopback request each (toward TEST-NET-3, RFC 5737 -- guaranteed unroutable, so no real
network dependency and no reliance on any host actually answering) and assert the guarded
context recorded it as a violation rather than letting it reach the network.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from tests.harnesses.browser import (
    GuardedContext,
    LoopbackFakeService,
    install_egress_guard,
    loopback_fake_service,
)

pytestmark = pytest.mark.playwright

# RFC 5737 TEST-NET-3: reserved for documentation, guaranteed never to route anywhere real.
_NON_LOOPBACK = "http://203.0.113.1"


@pytest.fixture(scope="module")
def service() -> AsyncIterator[LoopbackFakeService]:
    with loopback_fake_service() as svc:
        yield svc


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


async def _new_page(context: BrowserContext) -> Page:
    return await context.new_page()


# --------------------------------------------------------------------------------------------
# BROWSER-LOCAL
# --------------------------------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="BROWSER-LOCAL-001", context_id="browser", lane="browser")
async def test_capture_schedule_post(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(service.base_url + "/")
    result = await page.evaluate(
        """async (url) => {
            const body = new URLSearchParams({getUnitClass: 'true', attendeeID: '90000001'});
            const response = await fetch(url, {method: 'POST', body: body.toString(),
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
            return await response.json();
        }""",
        service.base_url + "/mobile/inc/ajax_mobile.php",
    )
    assert result["status"]["status"] == 1
    assert result["data"][0]["classP4ID"] == "2000001"
    guard.assert_clean()


@pytest.mark.matrix_case(case_id="BROWSER-LOCAL-002", context_id="browser", lane="browser")
async def test_serve_requirement_json(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(service.base_url + "/")
    result = await page.evaluate(
        """async (url) => {
            const body = new URLSearchParams({getClassRequirement: 'true', classP4ID: '2000001',
                attendeeID: '90000001'});
            const response = await fetch(url, {method: 'POST', body: body.toString(),
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
            return await response.json();
        }""",
        service.base_url + "/mobile/inc/ajax_mobile.php",
    )
    assert result["status"]["status"] == 1
    assert result["data"][0]["REQ_NBR_WEB_DISPLAY"] == "#1"
    guard.assert_clean()


@pytest.mark.matrix_case(case_id="BROWSER-LOCAL-003", context_id="browser", lane="browser")
async def test_real_interception(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    # Proves the guard is wired to a REAL Playwright request event, not a no-op: a loopback
    # navigation must show up in guard.allowed (populated only by the route handler actually
    # running), and nothing lands in guard.violations.
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(service.base_url + "/")
    assert "127.0.0.1" in guard.allowed
    guard.assert_clean()


@pytest.mark.matrix_case(case_id="BROWSER-LOCAL-004", context_id="browser", lane="browser")
async def test_full_local_acquisition_success(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(service.base_url + "/")
    ajax_url = service.base_url + "/mobile/inc/ajax_mobile.php"
    schedule = await page.evaluate(
        """async (url) => {
            const body = new URLSearchParams({getUnitClass: 'true', attendeeID: '90000001'});
            const response = await fetch(url, {method: 'POST', body: body.toString(),
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
            return await response.json();
        }""",
        ajax_url,
    )
    assert schedule["status"]["status"] == 1
    class_p4_id = schedule["data"][0]["classP4ID"]
    requirement = await page.evaluate(
        """async ({url, classP4Id}) => {
            const body = new URLSearchParams({getClassRequirement: 'true', classP4ID: classP4Id,
                attendeeID: '90000001'});
            const response = await fetch(url, {method: 'POST', body: body.toString(),
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
            return await response.json();
        }""",
        {"url": ajax_url, "classP4Id": class_p4_id},
    )
    assert requirement["status"]["status"] == 1
    assert requirement["data"][0]["MERIT_BADGE_NAME"] == "Chess"
    guard.assert_clean()


# --------------------------------------------------------------------------------------------
# BROWSER-EGRESS: each attempts one non-loopback action and asserts it never reached the
# network -- the guard recorded a violation instead.
# --------------------------------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-001", context_id="browser", lane="browser")
async def test_egress_navigation_blocked(
    guarded: tuple[BrowserContext, GuardedContext],
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    with contextlib.suppress(Exception):  # an aborted navigation raises Playwright's Error type
        await page.goto(_NON_LOOPBACK, timeout=3000)
    assert guard.violations, "navigation to a non-loopback host was not blocked"


@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-002", context_id="browser", lane="browser")
async def test_egress_redirect_blocked(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    with contextlib.suppress(Exception):
        await page.goto(f"{service.base_url}/redirect?to={_NON_LOOPBACK}/", timeout=3000)
    assert guard.violations, "a redirect hop to a non-loopback host was not blocked"


@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-003", context_id="browser", lane="browser")
async def test_egress_frame_blocked(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(f"{service.base_url}/frame?to={_NON_LOOPBACK}/", timeout=3000)
    await page.wait_for_timeout(300)
    assert guard.violations, "a child frame's request to a non-loopback host was not blocked"


@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-004", context_id="browser", lane="browser")
async def test_egress_popup_blocked(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(f"{service.base_url}/popup?to={_NON_LOOPBACK}/", timeout=3000)
    await page.wait_for_timeout(300)
    assert guard.violations, "a popup's navigation to a non-loopback host was not blocked"


@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-005", context_id="browser", lane="browser")
async def test_egress_worker_fetch_blocked(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    await page.goto(f"{service.base_url}/worker?to={_NON_LOOPBACK}/", timeout=3000)
    await page.wait_for_timeout(300)
    # Snapshot BEFORE any other action touches guard.violations: this is the only evidence
    # that the worker's own internal fetch() -- not some unrelated page-level request -- was
    # what the guard caught. Verified empirically against this Playwright/Chromium build:
    # context.route() DOES intercept a dedicated Worker's runtime fetch() calls (see the
    # harness module docstring), so this snapshot is a real, isolated proof of that path.
    assert guard.violations, "a worker's internal fetch() to a non-loopback host was not blocked"
    worker_violation_count = len(guard.violations)
    # A direct in-page fetch() exercises a different call site through the same route()
    # handler; asserted separately so it can never mask a broken worker-fetch guard above.
    result = await page.evaluate(
        """async (url) => {
            try { await fetch(url); return 'reached'; }
            catch (err) { return 'blocked'; }
        }""",
        _NON_LOOPBACK + "/",
    )
    assert result == "blocked"
    assert len(guard.violations) > worker_violation_count, (
        "the trailing page-level fetch() was not itself recorded as a violation"
    )


@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-006", context_id="browser", lane="browser")
async def test_egress_websocket_blocked(
    guarded: tuple[BrowserContext, GuardedContext], service: LoopbackFakeService
) -> None:
    context, guard = guarded
    page = await _new_page(context)
    # A reserved (RFC 2606), never-resolvable ".test" hostname rather than a raw IP: some
    # sandboxed network egress paths silently black-hole TCP SYNs to arbitrary IPs/ports
    # (no RST, no timeout signal for a long while), which starves the browser's own
    # "websocket" event of anything to report within a bounded test wait. A DNS failure is
    # immediate and portable everywhere, and is just as genuinely non-loopback.
    non_loopback_ws = "ws://external.invalid.example.test:81/"
    await page.goto(f"{service.base_url}/websocket?to={non_loopback_ws}", timeout=3000)
    await page.wait_for_timeout(500)
    assert guard.violations, "a WebSocket connection to a non-loopback host was not blocked"


@pytest.mark.matrix_case(case_id="BROWSER-EGRESS-007", context_id="browser", lane="browser")
async def test_egress_download_blocked() -> None:
    # A genuine end-to-end download aimed at a non-loopback host is unreachable through this
    # harness by construction: the same route() host check that blocks any other non-loopback
    # request (see BROWSER-EGRESS-001/002) runs and aborts before Chromium's download
    # subsystem ever receives a response, so page.on("download") never has anything to
    # observe for an external target -- confirmed empirically (direct navigation to a
    # non-loopback download URL, and a loopback page whose download link redirects
    # off-loopback, are both aborted at the route() layer before any "download" event fires).
    # This is therefore a direct, unit-style proof of the dedicated page.on("download", ...)
    # listener itself: a minimal fake BrowserContext/Page pair drives the REAL
    # ``install_egress_guard`` code path (not a reimplementation of its logic) and a fake
    # Download double exercises the real registered callback.
    from tests.harnesses.browser import install_egress_guard

    class _FakeContext:
        def __init__(self) -> None:
            self.pages: list[object] = []
            self.page_handler: object = None

        async def route(self, pattern: str, handler: object) -> None:
            del pattern, handler  # not exercised by this unit-style test

        def on(self, event: str, handler: object) -> None:
            if event == "page":
                self.page_handler = handler

    class _FakePage:
        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}

        def on(self, event: str, handler: object) -> None:
            self.handlers[event] = handler

    class _FakeDownload:
        def __init__(self, url: str) -> None:
            self.url = url

    context = _FakeContext()
    guard = await install_egress_guard(context)  # type: ignore[arg-type]
    assert context.page_handler is not None
    page = _FakePage()
    context.page_handler(page)  # type: ignore[misc, operator]
    assert "download" in page.handlers, "no download listener was registered on the page"

    page.handlers["download"](_FakeDownload("http://203.0.113.1/malware.exe"))
    assert guard.violations, "a download toward a non-loopback host was not recorded"
    assert "203.0.113.1" in guard.violations[-1]

    guard.violations.clear()
    page.handlers["download"](_FakeDownload("http://127.0.0.1:9/file.bin"))
    assert not guard.violations, "a loopback download was incorrectly flagged as a violation"


def test_browser_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.cases.acquisition_cases import (
        BROWSER_EGRESS_METADATA,
        BROWSER_LOCAL_METADATA,
    )
    from tests.matrix.model import Domain
    from tests.matrix.registry import validate_registry

    metas = list(BROWSER_LOCAL_METADATA) + list(BROWSER_EGRESS_METADATA)
    axes = [
        axis
        for axis in AXES
        if axis.domain is Domain.ACQUISITION and axis.axis_id in {"BROWSER-LOCAL", "BROWSER-EGRESS"}
    ]
    errors = validate_registry(metas, axes, [], [], [])
    assert errors == ()
