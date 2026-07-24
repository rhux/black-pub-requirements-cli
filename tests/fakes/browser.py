"""Strict fake Playwright Browser/Context/Page for driving real acquisition code (Task 19).

These fakes implement ONLY the attributes/methods ``scout_schedule_cli.navigate_and_trigger_schedule``
/ ``post_requirement`` / ``process_scout`` actually call on their page/context/browser objects --
read the real functions before adding anything here. Every response comes from the shared
``StrictScript`` so call order, attendee/class ids, and wait durations are strictly enforced.

``StrictFakePage.wait_for_timeout`` treats the ``navigate_and_trigger_schedule`` settle wait
(a fixed 1200ms, see ``scout_schedule_cli.py``) as internal plumbing -- it never sleeps and never
consumes the script -- because that value characterizes the navigation helper's own polling
mechanics, not the request-level behavior these cases pin. Every OTHER wait (a retry backoff or
the configured inter-class delay) is scripted and recorded on the shared ``FakeClock``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from tests.fakes.acquisition import AJAX_URL, StrictScript, schedule_post_data
from tests.fakes.clock import FakeClock

_NAV_SETTLE_MS = 1200


class _FakeRequest:
    __slots__ = ("post_data",)

    def __init__(self, post_data: str | None) -> None:
        self.post_data = post_data


class _FakeScheduleResponse:
    """Implements only what ``process_scout``/``is_schedule_response`` read off a Response."""

    def __init__(self, url: str, post_data: str | None, payload: Any) -> None:
        self.url = url
        self.request = _FakeRequest(post_data)
        self._payload = payload

    async def json(self) -> Any:
        return self._payload


class StrictFakeRouteRequest:
    __slots__ = ("url",)

    def __init__(self, url: str) -> None:
        self.url = url


class StrictFakeRoute:
    """Implements only what ``process_scout``'s ``block_dead_assets`` closure calls."""

    def __init__(self, url: str) -> None:
        self.request = StrictFakeRouteRequest(url)
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


class StrictFakePage:
    """Implements only the Page surface navigate_and_trigger_schedule/post_requirement use."""

    def __init__(self, script: StrictScript, clock: FakeClock) -> None:
        self._script = script
        self._clock = clock
        self._response_listeners: list[Callable[[Any], None]] = []
        self.default_timeout_ms: int | None = None
        self.closed = False

    def set_default_timeout(self, milliseconds: int) -> None:
        self.default_timeout_ms = milliseconds

    def on(self, event: str, callback: Callable[[Any], None]) -> None:
        if event == "response":
            self._response_listeners.append(callback)

    def remove_listener(self, event: str, callback: Callable[[Any], None]) -> None:
        if event == "response" and callback in self._response_listeners:
            self._response_listeners.remove(callback)

    async def goto(
        self, url: str, wait_until: str | None = None, timeout: int | None = None
    ) -> None:
        expected, response = self._script.next_schedule()
        post_data = schedule_post_data(expected.attendee_id)
        fake_response = _FakeScheduleResponse(AJAX_URL, post_data, response.value)
        # Mirrors real Playwright dispatch: navigate_and_trigger_schedule's on_response()
        # handler is itself synchronous and only schedules a task (asyncio.create_task); it does
        # not run inline. Calling the registered callback here reproduces that exactly.
        for callback in list(self._response_listeners):
            callback(fake_response)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        if milliseconds == _NAV_SETTLE_MS:
            # Yield once so the response-inspection task scheduled by goto() above gets a
            # chance to run and resolve navigate_and_trigger_schedule's future before it is
            # checked -- a real (but zero-delay) await, never a sleep tied to wall-clock time.
            await asyncio.sleep(0)
            return
        response = self._script.next_wait(milliseconds)
        self._clock.record(milliseconds)
        if response.error_type is not None:
            raise response.error_type(response.error_message)

    async def evaluate(self, script: str, arg: dict[str, Any] | None = None) -> Any:
        assert arg is not None, "only post_requirement's parameterized evaluate() is faked"
        attendee_id = str(arg["attendeeId"])
        class_id = str(arg["classP4Id"])
        response = self._script.next_requirement(attendee_id, class_id)
        if response.error_type is not None:
            raise response.error_type(response.error_message)
        return {"ok": True, "status": 200, "text": json.dumps(response.value)}

    async def close(self) -> None:
        self.closed = True


class StrictFakeContext:
    """Implements only the BrowserContext surface process_scout uses."""

    def __init__(self, script: StrictScript, clock: FakeClock) -> None:
        self._script = script
        self._clock = clock
        self.page: StrictFakePage | None = None
        self.closed = False
        self.route_pattern: str | None = None
        self.route_handler: Callable[[Any], Any] | None = None

    async def new_page(self) -> StrictFakePage:
        self.page = StrictFakePage(self._script, self._clock)
        return self.page

    async def route(self, pattern: str, handler: Callable[[Any], Any]) -> None:
        self.route_pattern = pattern
        self.route_handler = handler

    async def close(self) -> None:
        self.closed = True

    def assert_closed(self) -> None:
        if not self.closed:
            raise AssertionError("browser context was never closed")


class StrictFakeBrowser:
    """Implements ``Browser.new_context`` (called by ``process_scout``) and ``Browser.close``
    (called by ``async_main``'s own ``finally: await browser.close()`` one level above
    ``process_scout`` -- see ``scout_schedule_cli.py:1862-1863``)."""

    def __init__(self, script: StrictScript, clock: FakeClock) -> None:
        self._script = script
        self._clock = clock
        self.contexts: list[StrictFakeContext] = []
        self.closed = False

    async def new_context(self, **kwargs: Any) -> StrictFakeContext:
        context = StrictFakeContext(self._script, self._clock)
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        self.closed = True
