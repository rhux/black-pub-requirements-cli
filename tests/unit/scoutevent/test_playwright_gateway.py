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
