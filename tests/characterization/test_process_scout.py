"""Characterize process_scout WITHOUT a browser (monkeypatch the 3 module-level fns).

Uses the real Task 19 strict fakes (``tests.fakes.browser`` / ``tests.fakes.acquisition``) for
the Browser/Context/Page surface that ``process_scout`` calls directly (``new_context``,
``new_page``, ``set_default_timeout``, ``on``, ``wait_for_timeout``, ``close``). ``_Resp``/
``_Request`` remain local: they stand in for the API *response payload* returned by the
monkeypatched ``navigate_and_trigger_schedule``, not for a Playwright browser object, so they are
not part of the Task 19 browser-fake surface.
"""

from __future__ import annotations

import argparse

import scout_schedule_cli as cli
from tests.factories.payloads import requirement_payload, schedule_payload
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse


class _Request:
    # process_scout reads schedule_response.request.post_data (:480) and form_values
    # extracts attendeeID from it -- that is the source of attendee_id, NOT the payload.
    def __init__(self, post_data: str = "attendeeID=90000001"):
        self.post_data = post_data


class _Resp:
    def __init__(self, payload, post_data: str = "attendeeID=90000001"):
        self._p = payload
        self.request = _Request(post_data)

    async def json(self):
        return self._p


def _args(**o):
    return argparse.Namespace(
        **{
            "timeout": 45,
            "request_delay_ms": 0,
            "allow_dead_assets": True,
            "headed": False,
            "channel": None,
            **o,
        }
    )


def _browser(
    script: tuple[tuple[ExpectedRequest, ScriptedResponse], ...] = (),
) -> StrictFakeBrowser:
    return StrictFakeBrowser(StrictScript(script), FakeClock())


async def test_process_scout_builds_records_without_browser(monkeypatch, tmp_path):
    async def nav(page, url, t):
        return _Resp(schedule_payload())

    async def name(page, fb):
        return fb

    async def post(page, aid, cpid):
        return requirement_payload()

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", post)

    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_browser(), scout, _args(), tmp_path)
    assert result.classes[0].class_name == "Chess"
    assert result.requirements[0].requirement_number == "#1"
    assert result.errors == ()


async def test_failing_scout_accumulates_error(monkeypatch, tmp_path):
    async def boom(page, url, t):
        raise RuntimeError("schedule exploded")

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", boom)
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_browser(), scout, _args(), tmp_path)
    assert result.errors and "schedule exploded" in " ".join(result.errors)


async def test_requirement_fetch_retries_three_times(monkeypatch, tmp_path):
    async def nav(page, url, t):
        return _Resp(schedule_payload())

    async def name(page, fb):
        return fb

    attempts = {"n": 0}

    async def flaky(page, aid, cpid):
        attempts["n"] += 1
        raise RuntimeError("transient")

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", flaky)
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    # process_scout's own retry loop backs off with page.wait_for_timeout(500 * attempt) on
    # every failed attempt (scout_schedule_cli.py:584); the strict fake page requires each wait
    # to be scripted in advance -- this is the retry policy at scout_schedule_cli.py:578
    # (range(1, 4), so 3 attempts / 3 waits of 500ms, 1000ms, 1500ms).
    script = tuple(
        (ExpectedRequest("wait", "", "", delay_ms=ms), ScriptedResponse())
        for ms in (500, 1000, 1500)
    )
    await cli.process_scout(_browser(script), scout, _args(), tmp_path)
    assert attempts["n"] == 3  # retry policy is range(1, 4) at scout_schedule_cli.py:538
