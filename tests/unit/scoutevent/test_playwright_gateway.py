"""NET-WIRE-002: the Playwright navigation gateway must consult assert_egress_allowed before
any navigation, and never navigate at all when the host is blocked. Two distinct stub pages are
used deliberately: the blocked-host test's stub must never reach a selector lookup at all (so it
raises AssertionError if one occurs), while the allowed-host test's stub DOES reach that code
path (egress passes, then the real navigate_and_trigger_schedule body runs its full selector/
click fallback against a page with no real response ever arriving) -- sharing one "selector
lookups always fail" stub between both tests would make the allowed-host test fail on the wrong
exception. This was a real bug in an earlier draft of this test file."""

from __future__ import annotations

import asyncio

import pytest

from scoutmb.adapters.scoutevent.playwright_gateway import (
    PlaywrightScoutingEventGateway,
    discover_name,
)
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

    def locator(self, selector: str) -> _EmptyLocator:
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


# =================================================================================================
# Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b B10.4):
# discover_name's selector-loop fallback and _fetch_schedule_on_page's selector-click/evaluate
# fallback -- both deliberately never exercised by the two egress tests above, which time out
# before reaching either loop.
# =================================================================================================


class _FakeLocator:
    def __init__(self, count: int, text: str = "", raises: bool = False) -> None:
        self._count = count
        self._text = text
        self._raises = raises
        self.clicked = False

    @property
    def first(self) -> _FakeLocator:
        return self

    async def count(self) -> int:
        if self._raises:
            raise RuntimeError("locator boom")
        return self._count

    async def inner_text(self) -> str:
        return self._text

    async def click(self, *, force: bool = False, timeout: int = 0) -> None:
        self.clicked = True


class _DiscoverPage:
    """Only implements what discover_name reads off a Page: .locator(selector)."""

    def __init__(self, locators: dict[str, _FakeLocator]) -> None:
        self._locators = locators

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators[selector]


async def test_discover_name_returns_fallback_immediately_when_provided() -> None:
    page = _DiscoverPage({})
    assert await discover_name(page, "Avery Archer") == "Avery Archer"


async def test_discover_name_selector_loop_recovers_from_exception_and_matches() -> None:
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    page = _DiscoverPage(
        {
            selectors[0]: _FakeLocator(0, raises=True),
            selectors[1]: _FakeLocator(1, text="Schedule"),  # excluded title -> keep looking
            selectors[2]: _FakeLocator(1, text="Avery Archer"),
            selectors[3]: _FakeLocator(0),
        }
    )
    assert await discover_name(page, "") == "Avery Archer"


async def test_discover_name_exhausts_selectors_and_returns_unknown() -> None:
    selectors = [
        "#scoutPage h1",
        "#scoutPage .ui-title",
        ".ui-page-active .ui-title",
        "h1.ui-title",
    ]
    page = _DiscoverPage({selector: _FakeLocator(0) for selector in selectors})
    assert await discover_name(page, "") == "Unknown Scout"


class _NavPage:
    """Only implements what _fetch_schedule_on_page reads off a Page/Response."""

    def __init__(
        self, locators: dict[str, _FakeLocator] | None = None, evaluate_resolves: bool = False
    ) -> None:
        self._locators = locators or {}
        self._listeners: list = []
        self._evaluate_resolves = evaluate_resolves
        self.evaluated = False

    def on(self, event: str, callback) -> None:
        if event == "response":
            self._listeners.append(callback)

    def remove_listener(self, event: str, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def goto(
        self, url: str, wait_until: str | None = None, timeout: int | None = None
    ) -> None:
        # A page can dispatch OTHER ajax responses before the schedule one -- is_schedule_response
        # must reject them without resolving the future.
        self._fire(matching=False)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        await asyncio.sleep(0)

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators[selector]

    def _fire(self, *, matching: bool = True) -> None:
        class _Resp:
            url = (
                "https://scoutingevent.com/mobile/ajax_mobile.php"
                if matching
                else "https://scoutingevent.com/mobile/unrelated.php"
            )

            class request:
                post_data = "getUnitClass=true&attendeeID=1" if matching else "other=1"

        for callback in list(self._listeners):
            callback(_Resp())

    async def evaluate(self, script: str) -> None:
        self.evaluated = True
        if self._evaluate_resolves:
            self._fire()


async def test_navigate_selector_loop_recovers_from_exception_then_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    selectors = [
        'a[href="#scoutPage"]',
        'a[href$="event.html#scoutPage"]',
        'a:has-text("Schedule")',
    ]

    class _ClickingLocator(_FakeLocator):
        async def click(self, *, force: bool = False, timeout: int = 0) -> None:
            self.clicked = True
            page._fire()  # clicking the real schedule link is what triggers the AJAX call

    page = _NavPage(
        {
            selectors[0]: _FakeLocator(0, raises=True),
            selectors[1]: _ClickingLocator(1),
            selectors[2]: _FakeLocator(0),
        }
    )
    response = await PlaywrightScoutingEventGateway._fetch_schedule_on_page(
        page, "https://127.0.0.1/?t=X", 5
    )
    assert response is not None
    assert page._locators[selectors[1]].clicked


async def test_navigate_no_selector_matches_falls_back_to_evaluate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)
    selectors = [
        'a[href="#scoutPage"]',
        'a[href$="event.html#scoutPage"]',
        'a:has-text("Schedule")',
    ]
    page = _NavPage({selector: _FakeLocator(0) for selector in selectors}, evaluate_resolves=True)
    response = await PlaywrightScoutingEventGateway._fetch_schedule_on_page(
        page, "https://127.0.0.1/?t=X", 5
    )
    assert response is not None
    assert page.evaluated


# =================================================================================================
# Migrated from tests/characterization/test_phase_a_gap_closure.py: open_session's
# block_dead_assets route handler recovers when a request's URL can't be parsed into a hostname,
# continuing the route rather than aborting it.
# =================================================================================================


class _BadRouteRequest:
    url = None  # a non-string url makes re.sub raise inside block_dead_assets


class _BadRoute:
    def __init__(self) -> None:
        self.request = _BadRouteRequest()
        self.continued = False

    async def continue_(self) -> None:
        self.continued = True

    async def abort(self) -> None:
        raise AssertionError("must never abort a route whose hostname could not be parsed")


class _RoutingPage:
    async def close(self) -> None:
        return None


class _RoutingContext:
    def __init__(self) -> None:
        self.route_handler = None

    async def route(self, pattern: str, handler) -> None:
        self.route_handler = handler

    async def new_page(self) -> _RoutingPage:
        return _RoutingPage()

    async def close(self) -> None:
        return None


class _RoutingBrowser:
    def __init__(self) -> None:
        self.context = _RoutingContext()

    async def new_context(self, **kwargs) -> _RoutingContext:
        return self.context


async def test_block_dead_assets_recovers_when_url_is_unparseable() -> None:
    browser = _RoutingBrowser()
    gateway = PlaywrightScoutingEventGateway(browser, allow_dead_assets=False)  # type: ignore[arg-type]

    async with gateway.open_session():
        pass

    assert browser.context.route_handler is not None
    route = _BadRoute()
    await browser.context.route_handler(route)
    assert route.continued is True
