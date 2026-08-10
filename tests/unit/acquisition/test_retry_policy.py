"""ACQ-BREAKER-001/002/003: consecutive-failure breaker. Below threshold stays closed; at
threshold opens; a success resets the count. The Sleeper/Jitter ports are fakes here -- no real
delay ever occurs in this test."""

from __future__ import annotations

import pytest

from scoutmb.features.acquisition.retry import BreakerOpen, RetryPolicy


class _RecordingSleeper:
    def __init__(self) -> None:
        self.slept_ms: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept_ms.append(seconds * 1000)

    def monotonic(self) -> float:
        return 0.0


class _ZeroJitter:
    def jitter(self, low: float, high: float) -> float:
        return low


@pytest.mark.matrix_case(case_id="ACQ-BREAKER-001", context_id="breaker", lane="default")
async def test_stays_closed_below_threshold() -> None:
    policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=3)
    policy.record_failure()
    policy.record_failure()
    assert policy.is_open is False


@pytest.mark.matrix_case(case_id="ACQ-BREAKER-002", context_id="breaker", lane="default")
async def test_opens_at_threshold_and_rejects_further_attempts() -> None:
    policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=3)
    policy.record_failure()
    policy.record_failure()
    policy.record_failure()
    assert policy.is_open is True
    with pytest.raises(BreakerOpen):
        policy.check_closed()


@pytest.mark.matrix_case(case_id="ACQ-BREAKER-003", context_id="breaker", lane="default")
async def test_success_resets_consecutive_failures() -> None:
    policy = RetryPolicy(sleeper=_RecordingSleeper(), jitter=_ZeroJitter(), breaker_threshold=3)
    policy.record_failure()
    policy.record_failure()
    policy.record_success()
    policy.record_failure()
    policy.record_failure()
    assert policy.is_open is False  # would have opened at 3 consecutive without the reset


async def test_backoff_delay_is_500ms_times_attempt_including_the_third(monkeypatch) -> None:
    sleeper = _RecordingSleeper()
    policy = RetryPolicy(sleeper=sleeper, jitter=_ZeroJitter(), breaker_threshold=99)
    await policy.wait_after_failure(1)
    await policy.wait_after_failure(2)
    await policy.wait_after_failure(3)
    assert sleeper.slept_ms == [500.0, 1000.0, 1500.0]
