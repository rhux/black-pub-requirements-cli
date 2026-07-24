"""Scale-profile allocation/pairing characterization (Task 22, Slice 1b Phase A).

Covers ``SCALE-000/001/002``, ``SCALE-SMALL-001..003``, ``SCALE-CANON-022``,
``SCALE-LARGE-050``, ``SCALE-PROP-001..002``, and ``SCALE-PAIR-001..002``. Every case here drives
the REAL ``tests.matrix.scale_profile`` primitives and ``tests.factories.scale`` generator --
never mocked -- and never touches ``raw_data/``: everything is deterministic synthetic data.
"""

from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.factories.scale import (
    CANONICAL_ATTENDEE_COUNT,
    CANONICAL_DEDUPED_CLASS_COUNT,
    CANONICAL_RAW_CLASS_COUNT,
    CANONICAL_REQUIREMENT_COUNT,
    DEDUPED_CLASS_COMPLETION_MARGINAL,
    FLAG_MARGINAL,
    HAS_REQUIREMENTS_MARGINAL,
    RAW_CLASS_COMPLETION_MARGINAL,
    SHAPE_MARGINAL,
    TYPE_MARGINAL,
    build_dataset,
    canonical_marginals,
    canonical_profile,
    profile,
)
from tests.matrix.scale_profile import (
    EvidenceKindForProfile,
    UnsupportedSyntheticCorrelation,
    allocate,
    require_supported,
)

pytestmark = pytest.mark.scale


# ---------------------------------------------------------------------------------------------
# SCALE-000/001/002
# ---------------------------------------------------------------------------------------------


def test_scale_000_zero_attendees() -> None:
    p = profile("SCALE-000", attendee_count=0, deduplicated_class_count=0)
    dataset = build_dataset(p)
    assert dataset.attendees == ()
    assert dataset.deduped_class_ids == ()
    assert dataset.requirement_rows == ()


def test_scale_001_one_attendee() -> None:
    p = profile("SCALE-001", attendee_count=1, deduplicated_class_count=3, requirement_count=6)
    dataset = build_dataset(p)
    assert len(dataset.attendees) == 1
    assert len(dataset.deduped_class_ids) == 3
    assert len(dataset.requirement_rows) == 6


def test_scale_002_shared_name_distinct_upstream_ids() -> None:
    p = profile("SCALE-002", attendee_count=2, deduplicated_class_count=4)
    dataset = build_dataset(p, name_overrides={0: "Shared Name", 1: "Shared Name"})
    first, second = dataset.attendees
    assert first.name == second.name == "Shared Name"
    # Distinct upstream identity (the real attendeeID bearer token) AND distinct per-run output
    # identity -- sharing a display name must never merge two attendees' identities.
    assert first.upstream_id != second.upstream_id
    assert first.output_id != second.output_id
    assert first.deduped_class_ids != second.deduped_class_ids


# ---------------------------------------------------------------------------------------------
# SCALE-SMALL-001..003: repeatable by profile version and seed.
# ---------------------------------------------------------------------------------------------


def _ordered_attendee_ids(seed: str, count: int, ordering: str) -> tuple[str, ...]:
    """Applies the case's declared "ordering" to the deterministically-built dataset's attendee
    upstream ids -- grouped (natural), reversed, or interleaved (odds-then-evens)."""
    p = profile(
        "SCALE-SMALL", attendee_count=count, deduplicated_class_count=count * 2, seed=seed
    )
    dataset = build_dataset(p)
    ids = [a.upstream_id for a in dataset.attendees]
    if ordering == "grouped":
        return tuple(ids)
    if ordering == "reversed":
        return tuple(reversed(ids))
    if ordering == "interleaved":
        return tuple(ids[0::2] + ids[1::2])
    raise ValueError(ordering)


@pytest.mark.parametrize(
    ("count", "ordering"),
    [(3, "grouped"), (7, "reversed"), (11, "interleaved")],
    ids=["SCALE-SMALL-001", "SCALE-SMALL-002", "SCALE-SMALL-003"],
)
def test_scale_small_repeatable_by_version_and_seed(count: int, ordering: str) -> None:
    same_seed_a = _ordered_attendee_ids("small-seed", count, ordering)
    same_seed_b = _ordered_attendee_ids("small-seed", count, ordering)
    assert same_seed_a == same_seed_b  # same version+seed -> identical output

    different_seed = _ordered_attendee_ids("other-seed", count, ordering)
    assert set(different_seed) == set(same_seed_a)  # same identities...
    # ...and for count > 1 a different seed changes the underlying attendee identities'
    # generation inputs enough that at least one upstream id differs in provenance from the
    # matching-count case; what must hold is that ordering/count is preserved and totals match
    # regardless of seed -- checked next.
    p = profile(
        "SCALE-SMALL", attendee_count=count, deduplicated_class_count=count * 2, seed="other-seed"
    )
    dataset = build_dataset(p)
    assert sum(len(a.deduped_class_ids) for a in dataset.attendees) == count * 2
    assert len({a.upstream_id for a in dataset.attendees}) == count  # identity isolation


# ---------------------------------------------------------------------------------------------
# SCALE-CANON-022: exact canonical topology + every authoritative marginal.
# ---------------------------------------------------------------------------------------------


def test_scale_canon_022_topology() -> None:
    dataset = build_dataset(canonical_profile())
    assert len(dataset.attendees) == CANONICAL_ATTENDEE_COUNT
    assert len(dataset.deduped_class_ids) == CANONICAL_DEDUPED_CLASS_COUNT
    assert len(dataset.raw_class_rows) == CANONICAL_RAW_CLASS_COUNT
    assert len(dataset.requirement_rows) == CANONICAL_REQUIREMENT_COUNT

    per_attendee_counts = Counter(len(a.deduped_class_ids) for a in dataset.attendees)
    assert per_attendee_counts == Counter({5: 10, 4: 12})

    # 103 raw = 98 deduplicated + 5 duplicates, one per attendee among the first five.
    duplicated_attendees = [a for a in dataset.attendees if len(a.raw_class_ids) > len(a.deduped_class_ids)]
    assert len(duplicated_attendees) == 5
    assert {a.index for a in duplicated_attendees} == {0, 1, 2, 3, 4}


def test_scale_canon_022_every_authoritative_marginal() -> None:
    marginals = canonical_marginals(build_dataset(canonical_profile()))
    assert marginals["flag_marginal"] == FLAG_MARGINAL
    assert marginals["type_marginal"] == TYPE_MARGINAL
    assert marginals["raw_completion_marginal"] == RAW_CLASS_COMPLETION_MARGINAL
    assert marginals["deduped_completion_marginal"] == DEDUPED_CLASS_COMPLETION_MARGINAL
    assert marginals["has_req_marginal"] == HAS_REQUIREMENTS_MARGINAL
    assert marginals["shape_marginal"] == SHAPE_MARGINAL


def test_scale_canon_022_stable_same_seed_bytes() -> None:
    """Same (profile_version, seed) -> byte-identical (structurally-equal) output."""
    first = canonical_marginals(build_dataset(canonical_profile(profile_version=3, seed="pin")))
    second = canonical_marginals(build_dataset(canonical_profile(profile_version=3, seed="pin")))
    assert first == second

    first_dataset = build_dataset(canonical_profile(profile_version=3, seed="pin"))
    second_dataset = build_dataset(canonical_profile(profile_version=3, seed="pin"))
    assert first_dataset.attendees == second_dataset.attendees
    assert first_dataset.requirement_rows == second_dataset.requirement_rows


def test_scale_canon_022_different_seed_reorders_but_marginals_hold() -> None:
    baseline = build_dataset(canonical_profile(seed="seed-a"))
    other = build_dataset(canonical_profile(seed="seed-b"))

    baseline_order = [row.requirement_number for row in baseline.requirement_rows]
    other_order = [row.requirement_number for row in other.requirement_rows]
    assert baseline_order != other_order  # different seed -> different order...

    # ...but every authoritative marginal (a partition total) is unaffected by which row lands
    # where.
    assert canonical_marginals(other)["flag_marginal"] == FLAG_MARGINAL
    assert canonical_marginals(other)["shape_marginal"] == SHAPE_MARGINAL
    assert sum(canonical_marginals(other)["flag_marginal"].values()) == CANONICAL_REQUIREMENT_COUNT


# ---------------------------------------------------------------------------------------------
# SCALE-LARGE-050
# ---------------------------------------------------------------------------------------------


def test_scale_large_050_deterministic_allocation_and_request_count() -> None:
    p = profile("SCALE-LARGE-050", attendee_count=50, deduplicated_class_count=150)
    dataset_a = build_dataset(p)
    dataset_b = build_dataset(p)
    assert dataset_a.attendees == dataset_b.attendees  # deterministic allocation/order

    nonblank_deduped_class_ids = [cid for cid in dataset_a.deduped_class_ids if cid]
    # Request count equals nonblank deduplicated class IDs (+ implicit one schedule request per
    # attendee, asserted directly in tests/performance/test_phase_a_baseline.py's PERF-REQ-003).
    assert len(nonblank_deduped_class_ids) == 150
    assert len(dataset_a.attendees) == 50


# ---------------------------------------------------------------------------------------------
# SCALE-PROP-001/002: bounded Hypothesis-style counts 0-60.
# ---------------------------------------------------------------------------------------------


@given(attendee_count=st.integers(min_value=0, max_value=60))
@settings(max_examples=40, deadline=None)
def test_scale_prop_001_stable_ordering_and_identity_isolation(attendee_count: int) -> None:
    p = profile(
        "SCALE-PROP-001",
        attendee_count=attendee_count,
        deduplicated_class_count=attendee_count * 2,
        seed=f"prop-{attendee_count}",
    )
    dataset = build_dataset(p)
    assert len(dataset.attendees) == attendee_count
    upstream_ids = [a.upstream_id for a in dataset.attendees]
    output_ids = [a.output_id for a in dataset.attendees]
    assert len(set(upstream_ids)) == attendee_count  # identity isolation
    assert len(set(output_ids)) == attendee_count

    # Rebuilding with the same profile is stable (arbitrary but stable ordering/grouping).
    rebuilt = build_dataset(p)
    assert [a.upstream_id for a in rebuilt.attendees] == upstream_ids


@given(attendee_count=st.integers(min_value=0, max_value=60))
@settings(max_examples=40, deadline=None)
def test_scale_prop_002_partition_totals_always_sum_correctly(attendee_count: int) -> None:
    deduplicated_class_count = attendee_count * 2
    p = profile(
        "SCALE-PROP-002",
        attendee_count=attendee_count,
        deduplicated_class_count=deduplicated_class_count,
        requirement_count=deduplicated_class_count * 3,
        seed=f"prop2-{attendee_count}",
    )
    dataset = build_dataset(p)
    assert sum(len(a.deduped_class_ids) for a in dataset.attendees) == deduplicated_class_count
    assert len(dataset.deduped_class_ids) == deduplicated_class_count
    assert len(dataset.requirement_rows) == deduplicated_class_count * 3
    assert sum(len(rows) for rows in dataset.requirements_by_class.values()) == len(
        dataset.requirement_rows
    )


# ---------------------------------------------------------------------------------------------
# SCALE-PAIR-001/002
# ---------------------------------------------------------------------------------------------


def test_scale_pair_001_reordering_one_marginal_leaves_others_unchanged() -> None:
    """Reordering ONE synthetic marginal pairing (here: the "shape" axis, by using a different
    seed that only the shape-pairing axis id would be sensitive to were it not independent)
    leaves the flag/type marginals and the class topology completely unchanged."""
    base = build_dataset(canonical_profile(seed="pair-base"))
    reordered = build_dataset(canonical_profile(seed="pair-reordered"))

    # Topology (independent of any requirement-row marginal) is unchanged.
    assert len(base.attendees) == len(reordered.attendees)
    assert len(base.deduped_class_ids) == len(reordered.deduped_class_ids)
    assert base.deduped_completion_marginal() == reordered.deduped_completion_marginal()

    # Each independent marginal assertion still holds after reordering.
    assert base.flag_marginal() == reordered.flag_marginal() == FLAG_MARGINAL
    assert base.type_marginal() == reordered.type_marginal() == TYPE_MARGINAL
    assert base.shape_marginal() == reordered.shape_marginal() == SHAPE_MARGINAL


def test_scale_pair_002_correlation_evidence_is_unsupported() -> None:
    p = canonical_profile()
    with pytest.raises(UnsupportedSyntheticCorrelation):
        require_supported(p, EvidenceKindForProfile.CORRELATION)

    # Every OTHER evidence kind remains supported (no exception).
    for kind in (
        EvidenceKindForProfile.MARGINAL,
        EvidenceKindForProfile.TOPOLOGY,
        EvidenceKindForProfile.ORDERING,
        EvidenceKindForProfile.REQUEST_COUNT,
    ):
        require_supported(p, kind)  # must not raise


# ---------------------------------------------------------------------------------------------
# allocate(): the shared largest-remainder helper, characterized directly.
# ---------------------------------------------------------------------------------------------


def test_allocate_canonical_class_layout() -> None:
    result = allocate(98, tuple((f"A{i}", 1) for i in range(22)))
    counts = Counter(result.values())
    assert counts == Counter({5: 10, 4: 12})
    assert sum(result.values()) == 98


def test_allocate_requirement_layout() -> None:
    result = allocate(4858, tuple((f"CLS-{i:05d}", 1) for i in range(98)))
    counts = Counter(result.values())
    assert counts == Counter({50: 56, 49: 42})
    assert sum(result.values()) == 4858


def test_scale_registry_is_structurally_valid() -> None:
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.scale_cases import ALL_SCALE_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    scale_axes = [axis for axis in AXES if axis.domain is Domain.SCALE]
    scale_boundaries = [b for b in BOUNDARIES if b.domain is Domain.SCALE]

    errors = validate_registry(
        ALL_SCALE_METADATA, scale_axes, scale_boundaries, [], list(POLICIES)
    )
    assert errors == ()
