"""Time and randomness, injected per collaborator rather than as one bag (D32).

Wall time is for persisted timestamps. Elapsed time and delays use a MONOTONIC source so a
wall-clock jump cannot affect retry, timeout, or shutdown behavior.
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class Sleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...
    def monotonic(self) -> float: ...


class Jitter(Protocol):
    def jitter(self, low: float, high: float) -> float: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class MonotonicSleeper:
    async def sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()


class SeededJitter:
    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def jitter(self, low: float, high: float) -> float:
        return self._random.uniform(low, high)
