from __future__ import annotations

import scout_schedule_cli as cli
from scoutmb.core.identity import attendee_filename_stem
from tests.factories.records import make_requirement


def test_stem_hides_the_raw_id_and_carries_the_full_uuid():
    stem = attendee_filename_stem("Avery Archer", "1234abcd-ef00-4000-8000-000000000000")
    assert stem == "avery-archer-1234abcdef0040008000000000000000"  # full 32 hex, no hyphens


def test_stem_distinct_for_distinct_output_ids():
    assert attendee_filename_stem(
        "Avery Archer", "aaaaaaaa-0000-4000-8000-000000000000"
    ) != attendee_filename_stem("Avery Archer", "bbbbbbbb-0000-4000-8000-000000000000")


def test_email_reports_do_not_collide_for_same_named_attendees(tmp_path):
    """write_email_reports must produce distinct .txt/.html for two same-named attendees."""

    def scout(aid, rid):
        return {
            "name": "Avery Archer",
            "attendee_id": aid,
            "classes": [],
            "errors": [],
            "requirements": [
                dict(
                    __import__("dataclasses").asdict(
                        make_requirement(
                            attendee_id=aid,
                            requirement_id=rid,
                            requirement_number="#1",
                            merit_badge_name="Chess",
                        )
                    )
                )
            ],
        }

    cli.write_email_reports(tmp_path, [scout("90000001", "r1"), scout("90000002", "r2")])
    txt = sorted((tmp_path / "emails").glob("avery-archer-*.txt"))
    # Two same-named attendees -> two distinct email files, not one overwritten file.
    assert len(txt) == 2 and txt[0].name != txt[1].name


def test_process_scout_raw_filenames_are_distinct_for_same_named(monkeypatch, tmp_path):
    """The raw side (inside process_scout) must also not collide. Reuses the Task 19 strict fakes."""
    import asyncio

    from tests.characterization.test_process_scout import _Resp
    from tests.factories.payloads import requirement_payload, schedule_payload
    from tests.fakes.acquisition import StrictScript
    from tests.fakes.browser import StrictFakeBrowser
    from tests.fakes.clock import FakeClock

    async def name(page, fb):
        return fb

    async def post(page, aid, cpid):
        return requirement_payload()

    monkeypatch.setattr(cli, "discover_name", name)
    monkeypatch.setattr(cli, "post_requirement", post)

    async def run(attendee_id):
        async def nav(page, url, t):
            return _Resp(schedule_payload(), post_data=f"attendeeID={attendee_id}")

        monkeypatch.setattr(cli, "navigate_and_trigger_schedule", nav)
        scout = cli.ScoutInput(name="Avery Archer", url="https://example.invalid/?t=TESTTOKEN0001")
        args = __import__("argparse").Namespace(
            timeout=45, request_delay_ms=0, allow_dead_assets=True, headed=False, channel=None
        )
        browser = StrictFakeBrowser(StrictScript(()), FakeClock())
        await cli.process_scout(browser, scout, args, tmp_path)

    asyncio.run(run("90000001"))
    asyncio.run(run("90000002"))
    schedules = sorted(tmp_path.glob("avery-archer-*-schedule.json"))
    assert len(schedules) == 2 and schedules[0].name != schedules[1].name
