"""ACQ-BREAKER/ACQ-RESUME end to end: a shared RetryPolicy sees failures across scouts (not
reset per scout), a checkpoint skips completed scouts and persists output-UUIDs across a
simulated process restart."""

from __future__ import annotations

from pathlib import Path

import pytest

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.files.checkpoint import AtomicFileCheckpointStore
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput, ScoutResult
from scoutmb.features.acquisition.batch import run_batch
from scoutmb.features.acquisition.retry import BreakerOpen, RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService
from scoutmb.ports.checkpoint_store import Checkpoint
from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock
from tests.matrix.cases.acquisition_cases import ExpectedRequest, ScriptedResponse


def _sched(attendee_id: str, payload: object) -> tuple[ExpectedRequest, ScriptedResponse]:
    """Local copy of acquisition_cases._sched -- deliberately NOT imported, since that name is
    module-private and this test module has no other reason to depend on the characterization
    catalog. A schedule request scripted to answer with `payload`."""
    return (ExpectedRequest("schedule", attendee_id), ScriptedResponse(value=payload))


def _schedule_payload(rows: tuple[dict[str, object], ...] = ()) -> dict[str, object]:
    """Local copy of acquisition_cases._schedule_payload -- see _sched's docstring."""
    return {"status": {"status": 1}, "data": list(rows)}


class _RecordingSleeper:
    async def sleep(self, seconds: float) -> None:
        pass

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


def _service(browser: StrictFakeBrowser, retry_policy: RetryPolicy) -> AcquisitionService:
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    return AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())


async def test_breaker_state_is_shared_across_scouts(tmp_path) -> None:
    """Two scouts, both scripted to fail their schedule fetch (nothing scripted -> the gateway's
    first call raises). A threshold-2 breaker must open on the SECOND scout's failure, proving
    the RetryPolicy instance -- not a fresh one per scout -- is what run_batch threads through."""
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=2)
    service = _service(browser, retry_policy)
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    run_identity = RunIdentity()

    scouts = [
        ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
        ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
        ScoutInput(name="Casey", url="https://scoutingevent.com/mobile/checkin?t=C"),
    ]

    with pytest.raises(BreakerOpen):
        await run_batch(
            scouts,
            service=service,
            retry_policy=retry_policy,
            checkpoint_store=checkpoint_store,
            run_identity=run_identity,
            config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
            raw_dir=tmp_path / "raw",
        )
    # The third scout ("Casey") must never have been attempted -- the breaker opened after the
    # second scout's failure, before a third BrowserContext could be opened.
    assert len(browser.contexts) == 2


async def test_completed_scout_is_skipped_on_resume(tmp_path) -> None:
    """A scout is skipped only when its URL is in BOTH completed_urls AND completed_results (the
    B5.3/B5.5 fourth-pass fix) -- a real run_batch save always writes both together, so this
    checkpoint populates completed_results too, matching what an actual completed run produces
    (as opposed to test_old_format_checkpoint_reprocesses_rather_than_drops_its_scout's
    deliberately old-format checkpoint, which has completed_urls but no completed_results and
    must be RE-processed, not skipped)."""
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    url = "https://scoutingevent.com/mobile/checkin?t=A"
    checkpoint_store.save(
        Checkpoint(
            version=1,
            completed_urls=(url,),
            output_ids={},
            completed_results={
                url: {
                    "name": "Avery", "qr_url": url, "attendee_id": "90000001",
                    "classes": [], "requirements": [], "errors": [],
                }
            },
        )
    )
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # nothing scripted -- must never be called
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = _service(browser, retry_policy)

    await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )
    assert browser.contexts == []  # never attempted -- the checkpoint already had it


async def test_output_uuid_survives_a_simulated_process_restart(tmp_path) -> None:
    """Save a checkpoint carrying a prior output_id for an attendee, then construct a BRAND NEW
    RunIdentity (simulating a fresh process) and hydrate it from that checkpoint -- the same
    attendee must resolve to the SAME output_id, not a freshly-minted one."""
    from scoutmb.core.identity import AttendeeId

    prior_output_id = "11111111-1111-4111-8111-111111111111"
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    checkpoint_store.save(
        Checkpoint(version=1, completed_urls=(), output_ids={"A1": prior_output_id})
    )

    fresh_run_identity = RunIdentity()
    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    fresh_run_identity.hydrate(checkpoint.output_ids)

    assert fresh_run_identity.output_id(AttendeeId.parse("A1")) == prior_output_id


async def test_checkpoint_file_exists_before_the_first_scout_is_processed(tmp_path) -> None:
    """ACQ-RESUME-001: a fresh run creates its checkpoint file at the START of the run, not
    only after the first scout happens to finish. Proven directly with a stand-in service whose
    process() checks the file's existence the moment it is called -- before it returns
    anything, so this cannot pass merely because run_batch eventually saves a checkpoint."""
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_store = AtomicFileCheckpointStore(checkpoint_path)
    observed_exists_when_processing_started: list[bool] = []

    class _ObservingService:
        async def process(
            self, *, scout: ScoutInput, config: AcquisitionConfig, raw_dir: Path,
            run_identity: RunIdentity,
        ) -> ScoutResult:
            observed_exists_when_processing_started.append(checkpoint_path.exists())
            return ScoutResult(name=scout.name, qr_url=scout.url, attendee_id="A1")

    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)

    await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=_ObservingService(),  # type: ignore[arg-type] -- duck-types AcquisitionService
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )

    assert observed_exists_when_processing_started == [True]


async def test_failed_scout_is_not_marked_completed_and_is_retried_on_resume(tmp_path) -> None:
    """A scout whose ScoutResult.errors is non-empty must NOT be added to completed_urls or
    completed_results -- otherwise one transient failure would permanently skip that scout on
    every future resume instead of retrying it. output_ids IS still saved, since a scout's
    output_id, once minted, must stay stable across retries."""
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    clock = FakeClock()
    browser = StrictFakeBrowser(StrictScript(()), clock)  # nothing scripted -- schedule fetch fails
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = _service(browser, retry_policy)

    results = await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )
    assert len(results) == 1
    assert results[0].errors  # the scout failed -- fetch_schedule is never retried, see B5.4

    loaded = checkpoint_store.load()
    assert loaded is not None
    assert "https://scoutingevent.com/mobile/checkin?t=A" not in loaded.completed_urls
    assert loaded.completed_results == {}


async def test_resumed_run_report_includes_previously_completed_scouts(tmp_path) -> None:
    """A checkpoint's completed_results carries enough of each successful ScoutResult to
    reconstruct it on resume. The SECOND run_batch call's returned list must include the FIRST
    run's scout (reconstructed via scout_result_from_row) alongside the newly processed one --
    a resumed run's report must not silently drop scouts finished on a prior process."""
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")

    clock_1 = FakeClock()
    script_1 = StrictScript((_sched("90000001", _schedule_payload()),))
    browser_1 = StrictFakeBrowser(script_1, clock_1)
    retry_policy_1 = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service_1 = _service(browser_1, retry_policy_1)

    first_results = await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=service_1,
        retry_policy=retry_policy_1,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )
    script_1.assert_consumed()
    assert len(first_results) == 1
    assert not first_results[0].errors

    clock_2 = FakeClock()
    script_2 = StrictScript((_sched("90000002", _schedule_payload()),))
    browser_2 = StrictFakeBrowser(script_2, clock_2)
    retry_policy_2 = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service_2 = _service(browser_2, retry_policy_2)

    second_results = await run_batch(
        [
            ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
            ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
        ],
        service=service_2,
        retry_policy=retry_policy_2,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )
    script_2.assert_consumed()
    assert len(browser_2.contexts) == 1  # only Bailey touched the browser -- Avery was skipped
    assert {result.attendee_id for result in second_results} == {"90000001", "90000002"}


async def test_old_format_checkpoint_reprocesses_rather_than_drops_its_scout(tmp_path) -> None:
    """A checkpoint saved before completed_results existed (Task B5.3's backward-compat load,
    tests/unit/acquisition/test_checkpointing.py::test_checkpoint_without_completed_results_key_
    is_backward_compatible) has a URL in completed_urls with NOTHING in completed_results to
    reconstruct it from. Skipping on completed_urls alone would silently drop that scout from
    this run's results -- the exact bug completed_results exists to prevent, just triggered by an
    old-format file. run_batch must re-process it instead: still present in the final results,
    with a fresh BrowserContext actually opened for it."""
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_store = AtomicFileCheckpointStore(checkpoint_path)
    # Hand-write an old-format checkpoint: completed_urls populated, no completed_results key at
    # all -- exactly what a pre-B5.3 save (or a hand-edited file) would look like on disk.
    import json

    checkpoint_path.write_text(
        json.dumps(
            {
                "version": 1,
                "completed_urls": ["https://scoutingevent.com/mobile/checkin?t=A"],
                "output_ids": {},
            }
        ),
        encoding="utf-8",
    )

    clock = FakeClock()
    script = StrictScript((_sched("90000001", _schedule_payload()),))
    browser = StrictFakeBrowser(script, clock)
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = _service(browser, retry_policy)

    results = await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )
    script.assert_consumed()
    assert len(browser.contexts) == 1  # re-processed, not silently skipped
    assert {result.attendee_id for result in results} == {"90000001"}


async def test_scout_delay_is_slept_between_scouts_but_not_after_the_last(tmp_path) -> None:
    """Legacy async_main sleeps between scouts (never after the last one) using
    scout_delay_ms/1000 seconds when scout_delay_ms is given -- an earlier draft of run_batch
    dropped this pacing entirely. Sleeping through retry_policy.sleeper keeps this fake-clock
    -testable rather than a real asyncio.sleep."""

    class _DelayRecordingSleeper:
        def __init__(self) -> None:
            self.slept_seconds: list[float] = []

        async def sleep(self, seconds: float) -> None:
            self.slept_seconds.append(seconds)

        def monotonic(self) -> float:
            return 0.0

    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    clock = FakeClock()
    script = StrictScript(
        (
            _sched("90000001", _schedule_payload()),
            _sched("90000002", _schedule_payload()),
        )
    )
    browser = StrictFakeBrowser(script, clock)
    sleeper = _DelayRecordingSleeper()
    retry_policy = RetryPolicy(sleeper=sleeper, jitter=_ZeroJitter(), breaker_threshold=99)
    service = _service(browser, retry_policy)

    await run_batch(
        [
            ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A"),
            ScoutInput(name="Bailey", url="https://scoutingevent.com/mobile/checkin?t=B"),
        ],
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
        scout_delay_ms=250,
    )
    script.assert_consumed()
    assert sleeper.slept_seconds == [0.25]  # exactly one delay -- between the two scouts, not after


async def test_run_batch_prints_legacy_style_progress(tmp_path, capsys) -> None:
    """Nothing else in the CLI path produces this operator-facing progress output -- an earlier
    draft of run_batch dropped it when the inline async_main loop was extracted."""
    checkpoint_store = AtomicFileCheckpointStore(tmp_path / "checkpoint.json")
    clock = FakeClock()
    script = StrictScript((_sched("90000001", _schedule_payload()),))
    browser = StrictFakeBrowser(script, clock)
    retry_policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99)
    service = _service(browser, retry_policy)

    await run_batch(
        [ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=A")],
        service=service,
        retry_policy=retry_policy,
        checkpoint_store=checkpoint_store,
        run_identity=RunIdentity(),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
    )

    out = capsys.readouterr().out
    assert "[1/1] Avery" in out
    assert "attendeeID=90000001, classes=0, requirements=0, errors=0" in out
