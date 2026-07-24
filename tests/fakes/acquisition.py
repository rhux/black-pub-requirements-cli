"""Strict scripted-call bookkeeping for the acquisition fakes (Task 19).

``StrictScript`` owns the shared deque of ``(ExpectedRequest, ScriptedResponse)`` pairs that
back ``tests/fakes/browser.py``'s fake Playwright page/context/browser. It compares the next
complete request against what the legacy code actually did, raises ``UnexpectedFakeCall`` on
any mismatch (wrong id, wrong order, wrong delay, an unexpected extra call), and raises
``UnconsumedFakeResponses`` from ``assert_consumed()`` if anything scripted was never used.

This module also holds the one plain building block the ``form``-context runner needs to call
``scout_schedule_cli.form_values`` / ``is_schedule_response`` directly: ``FormResponseStub``, a
minimal stand-in implementing only the two attributes those two functions read
(``response.url`` and ``response.request.post_data``).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

AJAX_URL = "https://scoutingevent.com/mobile/inc/ajax_mobile.php"


class UnexpectedFakeCall(AssertionError):
    """A fake received a call that does not match the next scripted expectation."""


class UnconsumedFakeResponses(AssertionError):
    """``assert_consumed()`` found scripted responses the code under test never asked for."""


def schedule_post_data(attendee_id: str) -> str:
    """The exact query-string shape ``form_values`` must parse back to ``attendeeID``."""
    return f"getUnitClass=true&attendeeID={attendee_id}"


@dataclass(frozen=True, slots=True)
class _FakeRequest:
    post_data: str | None


class FormResponseStub:
    """Implements only what ``is_schedule_response`` reads: ``.url`` and ``.request.post_data``."""

    def __init__(self, url: str, post_data: str | None) -> None:
        self.url = url
        self.request = _FakeRequest(post_data)


class StrictScript:
    """The strict call-order/parameter contract shared by every acquisition fake."""

    def __init__(self, script: tuple[tuple[ExpectedRequest, ScriptedResponse], ...]) -> None:
        self._pending: deque[tuple[ExpectedRequest, ScriptedResponse]] = deque(script)
        self.calls: list[ExpectedRequest] = []

    def _pop(self, operation: str) -> tuple[ExpectedRequest, ScriptedResponse]:
        if not self._pending:
            raise UnexpectedFakeCall(f"extra {operation!r} call with no script remaining")
        expected, response = self._pending[0]
        if expected.operation != operation:
            raise UnexpectedFakeCall(
                f"expected a {expected.operation!r} call next, got {operation!r}"
            )
        self._pending.popleft()
        self.calls.append(expected)
        return expected, response

    def next_schedule(self) -> tuple[ExpectedRequest, ScriptedResponse]:
        return self._pop("schedule")

    def next_requirement(self, attendee_id: str, class_id: str) -> ScriptedResponse:
        from tests.matrix.cases.acquisition_cases import ExpectedRequest

        expected, response = self._pop("requirement")
        actual = ExpectedRequest("requirement", attendee_id, class_id)
        if (expected.attendee_id, expected.class_id) != (actual.attendee_id, actual.class_id):
            raise UnexpectedFakeCall(f"expected {expected!r}, got {actual!r}")
        return response

    def next_wait(self, delay_ms: int) -> ScriptedResponse:
        expected, response = self._pop("wait")
        if expected.delay_ms != delay_ms:
            raise UnexpectedFakeCall(f"expected a {expected.delay_ms}ms wait, got {delay_ms}ms")
        return response

    def assert_consumed(self) -> None:
        if self._pending:
            raise UnconsumedFakeResponses(
                f"{len(self._pending)} scripted response(s) were never consumed: "
                f"{[expected for expected, _ in self._pending]!r}"
            )
