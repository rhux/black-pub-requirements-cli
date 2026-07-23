"""Proves the strict-fake misuse contract itself (Task 19, FAKE-STRICT-001..007).

Each test drives ``tests/fakes/acquisition.StrictScript`` (directly, or through
``tests/fakes/browser.StrictFakePage`` where the scenario is call-shaped rather than
data-shaped) and asserts it fails LOUDLY and EXACTLY as designed: a wrong id, a wrong call
order, a wrong wait duration, an unscripted extra call, or a script left over at the end all
raise -- they never silently pass.
"""

from __future__ import annotations

import pytest

from tests.fakes.acquisition import (
    StrictScript,
    UnconsumedFakeResponses,
    UnexpectedFakeCall,
)
from tests.fakes.browser import StrictFakePage
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

_SCHEDULE_PAYLOAD = {"status": {"status": 1}, "data": []}
_REQUIREMENT_PAYLOAD = {"status": {"status": 1}, "data": []}


def _req(attendee_id: str, class_id: str) -> tuple[ExpectedRequest, ScriptedResponse]:
    return (
        ExpectedRequest("requirement", attendee_id, class_id),
        ScriptedResponse(value=_REQUIREMENT_PAYLOAD),
    )


def _wait(ms: int) -> tuple[ExpectedRequest, ScriptedResponse]:
    return (ExpectedRequest("wait", "", "", ms), ScriptedResponse(value=None))


def _schedule(attendee_id: str) -> tuple[ExpectedRequest, ScriptedResponse]:
    return (
        ExpectedRequest("schedule", attendee_id),
        ScriptedResponse(value=_SCHEDULE_PAYLOAD),
    )


@pytest.mark.matrix_case(case_id="FAKE-STRICT-001", context_id="misuse", lane="default")
def test_wrong_attendee_id_raises() -> None:
    script = StrictScript((_req("90000001", "2000001"),))
    with pytest.raises(UnexpectedFakeCall):
        script.next_requirement("90000099", "2000001")


@pytest.mark.matrix_case(case_id="FAKE-STRICT-002", context_id="misuse", lane="default")
def test_wrong_class_id_raises() -> None:
    script = StrictScript((_req("90000001", "2000001"),))
    with pytest.raises(UnexpectedFakeCall):
        script.next_requirement("90000001", "2000099")


@pytest.mark.matrix_case(case_id="FAKE-STRICT-003", context_id="misuse", lane="default")
async def test_wrong_order_raises() -> None:
    # Scripted for a schedule call first; the code under test instead calls evaluate()
    # (requirement) with no prior goto() -- the fake must reject the reordering outright.
    script = StrictScript((_schedule("90000001"),))
    clock = FakeClock()
    page = StrictFakePage(script, clock)
    with pytest.raises(UnexpectedFakeCall):
        await page.evaluate("fetch(...)", {"attendeeId": "90000001", "classP4Id": "2000001"})


@pytest.mark.matrix_case(case_id="FAKE-STRICT-004", context_id="misuse", lane="default")
async def test_wrong_delay_raises() -> None:
    script = StrictScript((_wait(500),))
    clock = FakeClock()
    page = StrictFakePage(script, clock)
    with pytest.raises(UnexpectedFakeCall):
        await page.wait_for_timeout(999)


@pytest.mark.matrix_case(case_id="FAKE-STRICT-005", context_id="misuse", lane="default")
async def test_unexpected_retry_raises() -> None:
    # Only ONE requirement attempt was scripted; a second attempt (as a real retry loop would
    # issue on failure) finds nothing left and must raise rather than silently reusing the
    # last response.
    script = StrictScript((_req("90000001", "2000001"),))
    clock = FakeClock()
    page = StrictFakePage(script, clock)
    await page.evaluate("fetch(...)", {"attendeeId": "90000001", "classP4Id": "2000001"})
    with pytest.raises(UnexpectedFakeCall):
        await page.evaluate("fetch(...)", {"attendeeId": "90000001", "classP4Id": "2000001"})


@pytest.mark.matrix_case(case_id="FAKE-STRICT-006", context_id="misuse", lane="default")
async def test_extra_call_after_full_consumption_raises() -> None:
    script = StrictScript((_wait(500),))
    clock = FakeClock()
    page = StrictFakePage(script, clock)
    await page.wait_for_timeout(500)
    with pytest.raises(UnexpectedFakeCall):
        await page.wait_for_timeout(500)


@pytest.mark.matrix_case(case_id="FAKE-STRICT-007", context_id="misuse", lane="default")
def test_unconsumed_response_raises() -> None:
    script = StrictScript((_req("90000001", "2000001"), _wait(500)))
    script.next_requirement("90000001", "2000001")  # only the first entry is consumed
    with pytest.raises(UnconsumedFakeResponses):
        script.assert_consumed()
