"""Characterize process_scout WITHOUT a browser (monkeypatch the 3 module-level fns)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scout_schedule_cli as cli  # noqa: E402
from tests.factories.payloads import requirement_payload, schedule_payload  # noqa: E402


class _Request:
    # process_scout reads schedule_response.request.post_data (:480) and form_values
    # extracts attendeeID from it — that is the source of attendee_id, NOT the payload.
    def __init__(self, post_data: str = "attendeeID=90000001"):
        self.post_data = post_data


class _Resp:
    def __init__(self, payload, post_data: str = "attendeeID=90000001"):
        self._p = payload
        self.request = _Request(post_data)

    async def json(self):
        return self._p


class _Page:
    # process_scout calls these on the page BEFORE navigate (:472-476); the fake must
    # provide them or the test raises AttributeError before reaching the payload.
    def set_default_timeout(self, _ms):
        return None

    def on(self, _event, _cb):
        return None

    async def evaluate(self, *a, **k):
        return None

    async def wait_for_timeout(self, _ms):
        return None

    async def close(self):
        return None


class _Ctx:
    async def new_page(self):
        return _Page()

    async def route(self, *a, **k):
        return None

    async def close(self):
        return None


class _Browser:
    async def new_context(self, **k):
        return _Ctx()


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
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert result.classes[0].class_name == "Chess"
    assert result.requirements[0].requirement_number == "#1"
    assert result.errors == []


async def test_failing_scout_accumulates_error(monkeypatch, tmp_path):
    async def boom(page, url, t):
        raise RuntimeError("schedule exploded")

    monkeypatch.setattr(cli, "navigate_and_trigger_schedule", boom)
    scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
    result = await cli.process_scout(_Browser(), scout, _args(), tmp_path)
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
    await cli.process_scout(_Browser(), scout, _args(), tmp_path)
    assert attempts["n"] == 3  # retry policy is range(1, 4) at scout_schedule_cli.py:538
