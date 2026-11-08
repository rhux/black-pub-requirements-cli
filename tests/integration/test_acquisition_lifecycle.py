"""Every attendee-session resource closes, including when the gateway raises before the
session context manager's body completes."""

from __future__ import annotations

from tests.fakes.acquisition import StrictScript
from tests.fakes.browser import StrictFakeBrowser
from tests.fakes.clock import FakeClock

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.scoutevent.playwright_gateway import PlaywrightScoutingEventGateway
from scoutmb.core.identity import RunIdentity
from scoutmb.core.models import ScoutInput
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.features.acquisition.service import AcquisitionConfig, AcquisitionService


class _RecordingSleeper:
    async def sleep(self, seconds: float) -> None:
        pass

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


async def test_context_closes_even_when_schedule_fetch_raises(tmp_path) -> None:
    clock = FakeClock()
    script = StrictScript(())  # nothing scripted -> the gateway's first call raises immediately
    browser = StrictFakeBrowser(script, clock)
    gateway = PlaywrightScoutingEventGateway(browser)  # type: ignore[arg-type]
    retry_policy = RetryPolicy(
        sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=99
    )
    service = AcquisitionService(gateway=gateway, retry_policy=retry_policy, sink=AtomicFileSink())

    result = await service.process(
        scout=ScoutInput(name="Avery", url="https://scoutingevent.com/mobile/checkin?t=X"),
        config=AcquisitionConfig(timeout_seconds=5, request_delay_ms=0),
        raw_dir=tmp_path / "raw",
        run_identity=RunIdentity(),
    )

    assert result.errors  # the unscripted call failed and was recorded, not raised out
    assert browser.contexts, "a context must have been opened to fail inside"
    assert browser.contexts[0].closed is True
