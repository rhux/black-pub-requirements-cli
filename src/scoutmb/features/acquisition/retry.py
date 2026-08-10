"""Retry backoff (characterized, unchanged: 500ms x attempt for attempts 1-3, including the
wait after the third and final attempt) plus a consecutive-failure circuit breaker
(ACQ-BREAKER-001/002/003). Only ONE RetryPolicy instance exists per run (Task B5.5 constructs
it), so its breaker state is genuinely cumulative across scouts -- constructing a fresh instance
per scout (a bug an earlier draft of this plan had) makes the breaker permanently unable to
trip, since nothing then ever sees more than one scout's failures at a time."""

from __future__ import annotations

from dataclasses import dataclass, field

from scoutmb.errors import ScoutmbError
from scoutmb.ports.clock import Jitter, Sleeper


class BreakerOpen(ScoutmbError):
    """Consecutive failures reached the configured threshold; no further attempts are
    permitted until a success resets the count."""


@dataclass(slots=True)
class RetryPolicy:
    sleeper: Sleeper
    jitter: Jitter
    breaker_threshold: int
    _consecutive_failures: int = field(default=0, init=False)

    @property
    def is_open(self) -> bool:
        return self._consecutive_failures >= self.breaker_threshold

    def check_closed(self) -> None:
        if self.is_open:
            raise BreakerOpen(
                f"{self._consecutive_failures} consecutive failures reached the "
                f"threshold of {self.breaker_threshold}"
            )

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def record_success(self) -> None:
        self._consecutive_failures = 0

    async def wait_after_failure(self, attempt: int) -> None:
        """Named for when it is actually called -- after attempt N fails, before attempt N+1 (or
        before giving up, on the third). An earlier draft called this wait_before_attempt, which
        reads as running before EVERY attempt including the first; it never does."""
        base_seconds = (500 * attempt) / 1000
        jittered = base_seconds + self.jitter.jitter(0, base_seconds * 0.1)
        await self.sleeper.sleep(jittered)
