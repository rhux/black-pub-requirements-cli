from __future__ import annotations

import time
import uuid
from datetime import UTC

from scoutmb.ports.clock import MonotonicSleeper, SeededJitter, SystemClock
from scoutmb.ports.ids import Uuid4Factory


def test_clock_returns_timezone_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)


def test_seeded_jitter_is_reproducible() -> None:
    first = [SeededJitter(seed=7).jitter(0.5, 2.0) for _ in range(5)]
    second = [SeededJitter(seed=7).jitter(0.5, 2.0) for _ in range(5)]
    assert first == second
    assert all(0.5 <= value <= 2.0 for value in first)


def test_id_factory_makes_distinct_uuid4() -> None:
    factory = Uuid4Factory()
    values = {factory.new_id() for _ in range(100)}
    assert len(values) == 100
    for value in values:
        parsed = uuid.UUID(value)
        assert parsed.version == 4
        assert parsed.variant == uuid.RFC_4122


def test_monotonic_sleeper_monotonic_increases_across_calls() -> None:
    sleeper = MonotonicSleeper()
    first = sleeper.monotonic()
    second = sleeper.monotonic()
    assert isinstance(first, float)
    assert isinstance(second, float)
    assert second >= first
    # Sanity-check it tracks the same clock as time.monotonic(), not a fake.
    reference = time.monotonic()
    assert abs(reference - second) < 5.0


async def test_monotonic_sleeper_sleep_actually_awaits() -> None:
    sleeper = MonotonicSleeper()
    start = sleeper.monotonic()
    await sleeper.sleep(0.01)
    elapsed = sleeper.monotonic() - start
    assert elapsed >= 0.01
