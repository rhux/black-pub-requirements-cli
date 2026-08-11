"""B5 Task 1: process_scout must build the frozen, tuple-based ScoutResult -- not the legacy
mutable list-based one -- so `.classes`/`.requirements`/`.errors` are tuples and the object
supports dataclasses.replace()."""

from __future__ import annotations

import dataclasses

import pytest

from scoutmb.core.models import ScoutResult


def test_scout_result_instances_are_frozen_and_tuple_backed() -> None:
    result = ScoutResult(name="Avery", qr_url="https://x")
    assert isinstance(result.classes, tuple)
    assert isinstance(result.requirements, tuple)
    assert isinstance(result.errors, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.errors = ("boom",)  # type: ignore[misc]
    replaced = dataclasses.replace(result, errors=(*result.errors, "boom"))
    assert replaced.errors == ("boom",)
