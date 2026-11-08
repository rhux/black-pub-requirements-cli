"""B10.2: the breaker is genuinely shared across a whole pipeline run (not rebuilt per scout,
a real bug an earlier draft had), RunEvent.COMPLETE only follows a successful report, and a real
CancelledError maps to CANCEL/CANCELLED rather than FAIL. run_schedule_pipeline is pure DI --
every collaborator here is a plain fake or a real object built straight from a fake browser, no
async_playwright monkeypatching required."""

from __future__ import annotations

import asyncio

import pytest
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.config import ScheduleConfig
from scoutmb.core.models import ScoutInput
from scoutmb.core.run_state import RunState, RunStateMachine
from scoutmb.features.acquisition.pipeline import run_schedule_pipeline
from scoutmb.features.acquisition.retry import BreakerOpen, RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionService


class _RecordingSleeper:
    async def sleep(self, seconds: float) -> None:
        pass

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


def _config(tmp_path) -> ScheduleConfig:
    # `input` is required by ScheduleConfig but never read here -- scouts are injected directly.
    return ScheduleConfig(input=tmp_path / "unused.csv", output=tmp_path / "out")


class _NoOpReportingService:
    """A ReportingService stand-in for tests that never reach a successful publish (the breaker
    test below raises before the report step) -- duck-types ReportingService.publish's signature
    loosely via **kwargs since these tests only care THAT it was (or wasn't) called, never its
    output."""

    def publish(self, *args: object, **kwargs: object) -> None:
        pass


async def test_breaker_is_shared_across_the_whole_pipeline_run(tmp_path) -> None:
    """Three scouts, every schedule fetch scripted to fail (nothing scripted -> the gateway's
    first call raises), and a threshold-2 breaker -- the third scout must never be attempted,
    proving the SAME RetryPolicy instance run_schedule_pipeline threads into both the
    AcquisitionService AND run_batch sees both of the first two scouts' failures."""
    scouts = [
        ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
        ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
        ScoutInput(name="Casey", url="https://scoutingevent.com/mobile/checkin?t=C"),
    ]
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # nothing scripted -- every fetch fails
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(
        sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=2
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")

    with pytest.raises(BreakerOpen):
        await run_schedule_pipeline(
            _config(tmp_path),
            scouts=scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=_NoOpReportingService(),
        )
    # Casey must never have been attempted -- the breaker opened after Bailey's failure, before
    # a third BrowserContext could be opened.
    assert len(browser.contexts) == 2


async def test_complete_is_not_applied_until_reporting_succeeds(tmp_path) -> None:
    """A reporting failure after a clean (zero-scout) acquisition must leave the state machine
    in FAILED, never claim COMPLETED for a run that didn't actually finish publishing."""

    class _ExplodingReportingService:
        def publish(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated reporting failure")

    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # never called -- zero scouts
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(
        sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")
    run_state = RunStateMachine()

    with pytest.raises(RuntimeError, match="simulated reporting failure"):
        await run_schedule_pipeline(
            _config(tmp_path),
            scouts=[],
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=_ExplodingReportingService(),  # type: ignore[arg-type]
            run_state=run_state,
        )

    assert run_state.state is RunState.FAILED


async def test_cancellation_maps_to_cancel_not_fail(tmp_path) -> None:
    """A real asyncio.CancelledError (what a KeyboardInterrupt becomes inside the running
    coroutine once asyncio.run cancels it) maps to CANCEL then CANCELLED -- never FAIL. Injected
    at the reporting step, the last collaborator run_schedule_pipeline calls -- exactly as
    "realistic" a CancelledError source as any other await point inside the try block, and the
    simplest one to inject without touching run_batch's internals."""

    class _CancellingReportingService:
        def publish(self, *args: object, **kwargs: object) -> None:
            raise asyncio.CancelledError()

    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # never called -- zero scouts
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(
        sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")
    run_state = RunStateMachine()

    with pytest.raises(asyncio.CancelledError):
        await run_schedule_pipeline(
            _config(tmp_path),
            scouts=[],
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            reporting_service=_CancellingReportingService(),  # type: ignore[arg-type]
            run_state=run_state,
        )

    assert run_state.state is RunState.CANCELLED


async def test_progress_callback_and_pause_resume_events_fire_through_the_whole_run(
    tmp_path,
) -> None:
    """Migrated from tests/characterization/test_phase_a_gap_closure.py's async_main
    progress_callback/resume_event tests (retired in Slice 2b B10.4) -- every other test in this
    file drives run_schedule_pipeline with neither a progress_callback nor a resume_event, so the
    paused/resumed branches (and batch_start/scout_start/scout_done alongside them) are otherwise
    never taken for real."""
    scouts = [
        ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
        ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
    ]
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # nothing scripted -- every fetch fails
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(
        sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")

    events: list[dict] = []

    async def progress_callback(event: dict) -> None:
        events.append(event)

    resume_event = asyncio.Event()  # starts unset -> hits the "paused" branch

    async def set_resume_soon() -> None:
        await asyncio.sleep(0)
        resume_event.set()

    task = asyncio.ensure_future(set_resume_soon())
    result = await run_schedule_pipeline(
        _config(tmp_path),
        scouts=scouts,
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        reporting_service=_NoOpReportingService(),
        progress_callback=progress_callback,
        resume_event=resume_event,
    )
    await task

    assert result == 1  # both scouts failed (no schedule response) -> nonzero
    types = [event["type"] for event in events]
    assert types[0] == "batch_start"
    assert "paused" in types
    assert "resumed" in types
    assert "scout_start" in types
    assert "scout_done" in types


async def test_pause_resume_without_a_progress_callback_does_not_crash(tmp_path) -> None:
    """Same pause/resume branches, but with progress_callback=None -- the "if progress_callback
    is not None" guards around the paused/resumed events must be skipped, not just taken."""
    scouts = [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")]
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(
        sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "out" / "checkpoint.json")
    resume_event = asyncio.Event()

    async def set_resume_soon() -> None:
        await asyncio.sleep(0)
        resume_event.set()

    task = asyncio.ensure_future(set_resume_soon())
    result = await run_schedule_pipeline(
        _config(tmp_path),
        scouts=scouts,
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        reporting_service=_NoOpReportingService(),
        progress_callback=None,
        resume_event=resume_event,
    )
    await task
    assert result == 1
