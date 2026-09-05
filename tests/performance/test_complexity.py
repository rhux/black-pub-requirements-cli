from __future__ import annotations

import time

import pytest
from tests.factories.scale import (
    CANONICAL_ATTENDEE_COUNT,
    CANONICAL_DEDUPED_CLASS_COUNT,
    CANONICAL_REQUIREMENT_COUNT,
    build_dataset,
    canonical_profile,
    profile,
)

_SCALE_FACTOR = 8
# Real measurement (2026-09-05, this machine, best-of-3): canonical (4,858 requirement rows)
# took 9.96ms; an 8x-requirement-rows profile (38,864 rows) took 82.98ms -- a ~8.33x time
# growth against an 8x input growth, i.e. near-linear. The band below is deliberately generous
# (0.5x-3x the input-size ratio) to absorb timing noise at millisecond scale while still
# catching a real superlinear regression (a true O(n^2) blowup at this scale factor would show
# roughly a 64x time increase, far outside this band).
_MIN_GROWTH_RATIO = 0.5
_MAX_GROWTH_RATIO = 3.0


def _large_profile():
    return profile(
        "SCALE-PERF-BIG",
        attendee_count=CANONICAL_ATTENDEE_COUNT * _SCALE_FACTOR,
        deduplicated_class_count=CANONICAL_DEDUPED_CLASS_COUNT,
        raw_class_count=CANONICAL_DEDUPED_CLASS_COUNT,  # no duplicates -- simplest scaling
        requirement_count=CANONICAL_REQUIREMENT_COUNT * _SCALE_FACTOR,
    )


def _best_of(prof, repeats: int = 3) -> tuple[float, int]:
    best = float("inf")
    row_count = 0
    for _ in range(repeats):
        start = time.perf_counter()
        dataset = build_dataset(prof)
        best = min(best, time.perf_counter() - start)
        row_count = len(dataset.requirement_rows)
    return best, row_count


@pytest.mark.scale
def test_dataset_generation_time_grows_roughly_linearly_with_input_size():
    small_time, small_rows = _best_of(canonical_profile())
    large_time, large_rows = _best_of(_large_profile())

    input_ratio = large_rows / small_rows
    assert input_ratio == pytest.approx(_SCALE_FACTOR, rel=0.05)

    time_ratio = large_time / small_time
    assert _MIN_GROWTH_RATIO * input_ratio <= time_ratio <= _MAX_GROWTH_RATIO * input_ratio, (
        f"time grew {time_ratio:.2f}x for a {input_ratio:.2f}x input increase -- "
        f"outside the [{_MIN_GROWTH_RATIO}x, {_MAX_GROWTH_RATIO}x] linear-growth band"
    )
