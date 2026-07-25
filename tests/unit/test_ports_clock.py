from __future__ import annotations

from datetime import UTC

from scoutmb.ports.clock import SeededJitter, SystemClock
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
    assert all(len(value) == 36 for value in values)
