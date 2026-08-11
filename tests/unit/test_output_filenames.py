from __future__ import annotations

import pytest
from tests.factories.records import make_requirement

from scoutmb.core.identity import RunIdentity, attendee_filename_stem
from scoutmb.core.models import ScoutInput
from scoutmb.interfaces.cli.composition import build_reporting_service


def test_stem_hides_the_raw_id_and_carries_the_full_uuid():
    stem = attendee_filename_stem("Avery Archer", "1234abcd-ef00-4000-8000-000000000000")
    assert stem == "avery-archer-1234abcdef0040008000000000000000"  # full 32 hex, no hyphens


@pytest.mark.matrix_case(case_id="ART-NAME-008", context_id="filename", lane="default")
def test_stem_distinct_for_distinct_output_ids():
    """Two DIFFERENT attendees with the EXACT SAME display name still yield two different
    filename stems, because the per-run UUID is keyed on attendee_id (via RunIdentity.output_id),
    not on name."""
    assert attendee_filename_stem(
        "Avery Archer", "aaaaaaaa-0000-4000-8000-000000000000"
    ) != attendee_filename_stem("Avery Archer", "bbbbbbbb-0000-4000-8000-000000000000")


@pytest.mark.matrix_case(case_id="ART-EMAIL-004", context_id="email", lane="default")
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

    build_reporting_service()._write_email_reports(
        tmp_path, [scout("90000001", "r1"), scout("90000002", "r2")], run_identity=RunIdentity()
    )
    txt = sorted((tmp_path / "emails").glob("avery-archer-*.txt"))
    # Two same-named attendees -> two distinct email files, not one overwritten file.
    assert len(txt) == 2 and txt[0].name != txt[1].name


def test_process_scout_raw_filenames_are_distinct_for_same_named(tmp_path):
    """The raw side (inside AcquisitionService.process) must also not collide. Migrated off
    scout_schedule_cli.process_scout's old 4-positional-arg call onto AcquisitionService's real
    keyword-only API."""
    import asyncio

    from tests.fakes.acquisition import StrictScript
    from tests.fakes.browser import StrictFakeBrowser
    from tests.fakes.clock import FakeClock
    from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse

    from scoutmb.adapters.files.atomic import AtomicFileSink
    from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
    from scoutmb.features.acquisition.retry import RetryPolicy
    from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
    from scoutmb.ports.clock import MonotonicSleeper, SeededJitter

    async def run(attendee_id: str) -> None:
        script = StrictScript(
            (
                (
                    ExpectedRequest("schedule", attendee_id),
                    ScriptedResponse(value={"status": {"status": 1}, "data": []}),
                ),
            )
        )
        browser = StrictFakeBrowser(script, FakeClock())
        gateway = PlaywrightScoutingEventGateway(browser, allow_dead_assets=True)  # type: ignore[arg-type]
        retry_policy = RetryPolicy(sleeper=MonotonicSleeper(), jitter=SeededJitter(), breaker_threshold=99)
        service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
        scout = ScoutInput(name="Avery Archer", url="https://127.0.0.1/mobile/x?t=TESTTOKEN0001")
        await service.process(
            scout=scout,
            config=AcquisitionConfig(timeout_seconds=45, request_delay_ms=0),
            raw_dir=tmp_path,
            run_identity=RunIdentity(),
        )
        script.assert_consumed()

    asyncio.run(run("90000001"))
    asyncio.run(run("90000002"))
    schedules = sorted(tmp_path.glob("avery-archer-*-schedule.json"))
    assert len(schedules) == 2 and schedules[0].name != schedules[1].name
