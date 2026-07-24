"""Synthetic scale-profile data generation (Task 22, Slice 1b Phase A).

Builds a complete in-memory synthetic attendee/class/requirement dataset for a given
``ScaleProfile`` using ``tests.matrix.scale_profile``'s ``allocate``/``pairing_order``/
``synthetic_uuid4`` primitives. ``SCALE-CANON-022`` reproduces Task 16's authoritative aggregate
marginals (``FLAG_MARGINAL``/``TYPE_MARGINAL``/``RAW_CLASS_COMPLETION_MARGINAL``/
``DEDUPED_CLASS_COMPLETION_MARGINAL``/``HAS_REQUIREMENTS_MARGINAL``/``SHAPE_MARGINAL``) EXACTLY,
as SYNTHETIC data -- this module never reads ``raw_data/`` and never imports the legacy
application. Every generated identity (attendee names, class/requirement ids, descriptions) is a
deterministic synthetic string; nothing here is a real scout's data.

Serialization (where a test needs one, e.g. to prove "same version+seed -> byte-identical output")
must stay to profile metadata and aggregates only -- see ``canonical_marginals`` below, which is
the only thing any test should hash/compare across seeds. The full ``SyntheticDataset`` is an
in-memory structure for driving real production code (``tests/vertical``, ``tests/performance``);
it is never written to disk outside a test's own ``tmp_path``.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.factories.payloads import (
    REQUIREMENT_NUMBER_SHAPE_NOTATION,
    REQUIREMENT_NUMBER_SHAPES,
)
from tests.matrix.scale_profile import ScaleProfile, allocate, pairing_order, synthetic_uuid4

# ---------------------------------------------------------------------------------------------
# Authoritative aggregate contract (Task 16), reproduced here as the synthetic-generation target
# for SCALE-CANON-022 ONLY. Every other profile in this module is free-form deterministic data
# with no obligation to match these specific numbers.
# ---------------------------------------------------------------------------------------------

FLAG_MARGINAL: dict[tuple[str, str], int] = {
    ("0", "0"): 1409,
    ("0", "1"): 904,
    ("1", "0"): 1150,
    ("1", "1"): 1395,
}
TYPE_MARGINAL: dict[str, int] = {"1": 2225, "2": 1535, "3": 1098}
RAW_CLASS_COMPLETION_MARGINAL: dict[str, int] = {"0": 41, "1": 62}
DEDUPED_CLASS_COMPLETION_MARGINAL: dict[str, int] = {"0": 36, "1": 62}
HAS_REQUIREMENTS_MARGINAL: dict[str, int] = {"1": 103}
SHAPE_MARGINAL: dict[str, int] = {
    "": 31, "#(N)": 30, "#(a)": 72, "#A.": 12, "#N": 229, "#N(a)": 697,
    "#N(a)(N)": 104, "#N.": 545, "#N..Aaa.A.(N)": 50, "#N..Aaa.A.(N)(a)": 10,
    "#N..Aaa.A.(N)(a)(N)": 40, "#N.Aaaaaa.A(N)": 74, "#N.Aaaaaa.A.(N)": 140,
    "#N.Aaaaaa.A.(N)(a)": 56, "#N.AaaaaaA.(N)": 4, "#Na": 1064, "#Na(N)": 44,
    "#Na.": 469, "#Na[N]": 32, "Aaaa.": 125, "Aaaa.Aaaa.": 35, "Aaaa.N.": 30,
    "N": 65, "N.": 255, "N.a.": 520, "N.a.N.": 125,
}

_SHAPE_TO_CONCRETE: dict[str, str] = dict(
    zip(REQUIREMENT_NUMBER_SHAPE_NOTATION, REQUIREMENT_NUMBER_SHAPES, strict=True)
)

CANONICAL_ATTENDEE_COUNT = 22
CANONICAL_RAW_CLASS_COUNT = 103
CANONICAL_DEDUPED_CLASS_COUNT = 98
CANONICAL_REQUIREMENT_COUNT = 4858


def canonical_profile(*, profile_version: int = 1, seed: str = "canon") -> ScaleProfile:
    return ScaleProfile(
        profile_id="SCALE-CANON-022",
        schema_version=1,
        profile_version=profile_version,
        seed=seed,
        attendee_count=CANONICAL_ATTENDEE_COUNT,
        raw_class_count=CANONICAL_RAW_CLASS_COUNT,
        deduplicated_class_count=CANONICAL_DEDUPED_CLASS_COUNT,
        requirement_count=CANONICAL_REQUIREMENT_COUNT,
    )


def profile(
    profile_id: str,
    *,
    attendee_count: int,
    deduplicated_class_count: int,
    raw_class_count: int | None = None,
    requirement_count: int | None = None,
    profile_version: int = 1,
    seed: str = "default",
) -> ScaleProfile:
    """Construct a non-canonical ``ScaleProfile``. ``raw_class_count`` defaults to
    ``deduplicated_class_count`` (no duplicate rows); ``requirement_count`` defaults to one
    requirement per deduplicated class."""
    return ScaleProfile(
        profile_id=profile_id,
        schema_version=1,
        profile_version=profile_version,
        seed=seed,
        attendee_count=attendee_count,
        raw_class_count=raw_class_count if raw_class_count is not None else deduplicated_class_count,
        deduplicated_class_count=deduplicated_class_count,
        requirement_count=(
            requirement_count if requirement_count is not None else deduplicated_class_count
        ),
    )


@dataclass(frozen=True, slots=True)
class SyntheticAttendee:
    index: int
    output_id: str  # str(synthetic_uuid4(...)) -- test identity, not a production UUID claim
    upstream_id: str  # synthetic "attendee_id"-shaped bearer token, distinct from output_id
    name: str
    deduped_class_ids: tuple[str, ...]
    raw_class_ids: tuple[str, ...]  # includes duplicate entries, in schedule-response order
    raw_completions: tuple[str, ...]  # one "0"/"1" per raw_class_ids entry (independent per-row)


@dataclass(frozen=True, slots=True)
class SyntheticRequirementRow:
    class_id: str
    requirement_number: str  # concrete REQ_NBR_WEB_DISPLAY-shaped string
    shape: str  # contract shape notation, e.g. "#N."
    completed_req_flag: str
    completed_class_flag: str
    type_id: str


@dataclass(frozen=True, slots=True)
class SyntheticDataset:
    profile: ScaleProfile
    attendees: tuple[SyntheticAttendee, ...]
    class_completion: dict[str, str]  # deduped class_id -> "0"/"1"
    has_req: tuple[str, ...]  # one "0"/"1" per RAW class row, aligned with raw_class_rows order
    requirements_by_class: dict[str, tuple[SyntheticRequirementRow, ...]]

    @property
    def deduped_class_ids(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for attendee in self.attendees:
            for class_id in attendee.deduped_class_ids:
                seen.setdefault(class_id, None)
        return tuple(seen)

    @property
    def raw_class_rows(self) -> tuple[str, ...]:
        return tuple(cid for attendee in self.attendees for cid in attendee.raw_class_ids)

    @property
    def requirement_rows(self) -> tuple[SyntheticRequirementRow, ...]:
        return tuple(
            row for class_id in self.deduped_class_ids for row in self.requirements_by_class[class_id]
        )

    def raw_completion_marginal(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for attendee in self.attendees:
            for value in attendee.raw_completions:
                counts[value] = counts.get(value, 0) + 1
        return counts

    def deduped_completion_marginal(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for class_id in self.deduped_class_ids:
            value = self.class_completion[class_id]
            counts[value] = counts.get(value, 0) + 1
        return counts

    def has_req_marginal(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in self.has_req:
            counts[value] = counts.get(value, 0) + 1
        return counts

    def flag_marginal(self) -> dict[tuple[str, str], int]:
        counts: dict[tuple[str, str], int] = {}
        for row in self.requirement_rows:
            key = (row.completed_req_flag, row.completed_class_flag)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def type_marginal(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.requirement_rows:
            counts[row.type_id] = counts.get(row.type_id, 0) + 1
        return counts

    def shape_marginal(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.requirement_rows:
            counts[row.shape] = counts.get(row.shape, 0) + 1
        return counts


def _expand(marginal: dict) -> list:
    expanded: list = []
    for key, count in marginal.items():
        expanded.extend([key] * count)
    return expanded


def _assign_marginal(
    profile: ScaleProfile,
    axis_id: str,
    marginal: dict,
    row_count: int,
    reserved: dict[int, object] | None = None,
) -> list:
    """Expand ``marginal`` to ``row_count`` values and permute them onto row positions via the
    SHA-256 pairing order, honoring any ``reserved`` position -> forced-value overrides (used by
    the canonical generator to guarantee the five duplicate-target classes are "complete")."""
    reserved = reserved or {}
    remaining = dict(marginal)
    for value in reserved.values():
        remaining[value] = remaining.get(value, 0) - 1
        if remaining[value] < 0:
            raise ValueError(f"reserved value {value!r} exceeds marginal count")
    free_positions = [i for i in range(row_count) if i not in reserved]
    free_values = _expand(remaining)
    if len(free_values) != len(free_positions):
        raise ValueError("marginal total does not match row_count minus reserved positions")
    order = pairing_order(profile.profile_version, profile.seed, axis_id, len(free_positions))
    result: list = [None] * row_count
    for position, value in reserved.items():
        result[position] = value
    for slot_index, source_index in enumerate(order):
        result[free_positions[slot_index]] = free_values[source_index]
    return result


def _attendee_class_layout(profile: ScaleProfile) -> list[int]:
    """Per-attendee deduplicated class counts via largest-remainder ``allocate``, equal weights,
    attendee index order (the same mechanism the canonical profile uses -- ties break by
    ascending index, which is exactly why ``allocate(98, 22 equal weights)`` produces "the first
    ten attendees get five classes, the rest get four")."""
    if profile.attendee_count == 0:
        return []
    weighted = tuple((f"A{i}", 1) for i in range(profile.attendee_count))
    counts = allocate(profile.deduplicated_class_count, weighted)
    return [counts[f"A{i}"] for i in range(profile.attendee_count)]


def build_dataset(
    scale_profile: ScaleProfile,
    *,
    name_overrides: dict[int, str] | None = None,
) -> SyntheticDataset:
    """Build a full synthetic dataset for ``scale_profile``. Deterministic in
    ``(profile_version, seed)``: identical inputs produce byte-identical (structurally equal)
    output; a different ``seed`` changes ordering/pairing but never the marginal totals.

    ``name_overrides`` lets a caller force specific attendee display names (e.g. SCALE-002's
    "two attendees sharing a name but different upstream IDs") while every attendee still gets a
    distinct ``upstream_id``/``output_id`` -- identity is never derived from the display name.
    """
    name_overrides = name_overrides or {}
    per_attendee_counts = _attendee_class_layout(scale_profile)
    duplicate_count = scale_profile.raw_class_count - scale_profile.deduplicated_class_count
    if duplicate_count < 0:
        raise ValueError("raw_class_count must be >= deduplicated_class_count")
    if duplicate_count > scale_profile.attendee_count:
        raise ValueError("cannot add more duplicates than attendees in this generator")

    # Assign globally-unique deduplicated class ids to attendees in contiguous index blocks.
    class_ids_by_attendee: list[tuple[str, ...]] = []
    cursor = 0
    for count in per_attendee_counts:
        block = tuple(f"CLS-{cursor + i:05d}" for i in range(count))
        class_ids_by_attendee.append(block)
        cursor += count
    all_deduped_class_ids = tuple(f"CLS-{i:05d}" for i in range(cursor))

    # The reserved-position duplicate mechanism assumes deduplicated_class_count is large enough
    # that each of the first duplicate_count attendees has at least one class allocated --
    # validated above.
    for attendee_index in range(duplicate_count):
        if len(class_ids_by_attendee[attendee_index]) < 1:
            raise ValueError(
                f"cannot add a duplicate for attendee {attendee_index}: it was allocated 0 "
                "classes (increase deduplicated_class_count relative to attendee_count/"
                "duplicate_count for this profile)"
            )

    # Reserve the first `duplicate_count` attendees' FIRST class as forced-complete so that
    # adding one incomplete duplicate row for it reproduces "legacy dedup retains the completed
    # member" without perturbing the completion marginal (see module docstring / plan contract).
    reserved_complete: dict[int, str] = {}
    for attendee_index in range(duplicate_count):
        first_class = class_ids_by_attendee[attendee_index][0]
        reserved_complete[all_deduped_class_ids.index(first_class)] = "1"

    completion_marginal = (
        DEDUPED_CLASS_COMPLETION_MARGINAL
        if scale_profile.profile_id == "SCALE-CANON-022"
        else {"0": len(all_deduped_class_ids) // 2, "1": len(all_deduped_class_ids) - len(all_deduped_class_ids) // 2}
    )
    completion_values = _assign_marginal(
        scale_profile,
        "class-completion",
        completion_marginal,
        len(all_deduped_class_ids),
        reserved=dict(reserved_complete),
    )
    class_completion = dict(zip(all_deduped_class_ids, completion_values, strict=True))

    # Requirement counts per deduplicated class: largest-remainder allocation.
    if all_deduped_class_ids:
        weighted_classes = tuple((cid, 1) for cid in all_deduped_class_ids)
        req_counts = allocate(scale_profile.requirement_count, weighted_classes)
    else:
        req_counts = {}

    total_requirement_rows = sum(req_counts.values())
    if scale_profile.profile_id == "SCALE-CANON-022":
        flag_marginal: dict = dict(FLAG_MARGINAL)
        type_marginal: dict = dict(TYPE_MARGINAL)
        shape_marginal: dict = dict(SHAPE_MARGINAL)
    else:
        flag_marginal = {
            ("0", "1"): total_requirement_rows // 2,
            ("1", "0"): total_requirement_rows - total_requirement_rows // 2,
        }
        type_marginal = {"1": total_requirement_rows}
        shape_marginal = {"#N.": total_requirement_rows}

    flags = (
        _assign_marginal(scale_profile, "flag", flag_marginal, total_requirement_rows)
        if total_requirement_rows
        else []
    )
    types = (
        _assign_marginal(scale_profile, "type", type_marginal, total_requirement_rows)
        if total_requirement_rows
        else []
    )
    shapes = (
        _assign_marginal(scale_profile, "shape", shape_marginal, total_requirement_rows)
        if total_requirement_rows
        else []
    )

    requirements_by_class: dict[str, tuple[SyntheticRequirementRow, ...]] = {}
    row_cursor = 0
    for class_id in all_deduped_class_ids:
        count = req_counts.get(class_id, 0)
        rows = []
        for local_index in range(count):
            i = row_cursor + local_index
            shape = shapes[i]
            req_flag, class_flag = flags[i]
            rows.append(
                SyntheticRequirementRow(
                    class_id=class_id,
                    requirement_number=_SHAPE_TO_CONCRETE.get(shape, f"#{local_index + 1}"),
                    shape=shape,
                    completed_req_flag=req_flag,
                    completed_class_flag=class_flag,
                    type_id=types[i],
                )
            )
        requirements_by_class[class_id] = tuple(rows)
        row_cursor += count

    attendees: list[SyntheticAttendee] = []
    for index, deduped_ids in enumerate(class_ids_by_attendee):
        raw_ids = list(deduped_ids)
        raw_completions = [class_completion[cid] for cid in deduped_ids]
        if index < duplicate_count:
            # Insert one INCOMPLETE duplicate of the attendee's (forced-complete) first class,
            # right after the original -- "the incomplete member of an incomplete->complete pair
            # sharing one class ID; legacy dedup retains the completed member". The duplicate
            # row's own completion is independently "0", distinct from the retained original's
            # reserved "1" -- this is what makes raw completion == deduped completion + one "0"
            # per duplicate (41 == 36 + 5), exactly matching the authoritative contract.
            raw_ids = [deduped_ids[0], *deduped_ids]
            raw_completions = ["0", *raw_completions]
        attendees.append(
            SyntheticAttendee(
                index=index,
                output_id=str(synthetic_uuid4(scale_profile.profile_version, scale_profile.seed, index)),
                upstream_id=f"9{scale_profile.profile_version:03d}{index:06d}",
                name=name_overrides.get(index, f"Synthetic Scout {index:04d}"),
                deduped_class_ids=deduped_ids,
                raw_class_ids=tuple(raw_ids),
                raw_completions=tuple(raw_completions),
            )
        )

    # HAS_REQUIREMENTS_MARGINAL: every raw synthetic class row carries HAS_REQ="1" -- matching
    # the canonical contract's {"1": 103} exactly, and consistent with real process_scout never
    # gating a requirement request on HAS_REQ (see ACQ-HASREQ-002).
    has_req = tuple("1" for _ in (cid for attendee in attendees for cid in attendee.raw_class_ids))

    return SyntheticDataset(
        profile=scale_profile,
        attendees=tuple(attendees),
        class_completion=class_completion,
        has_req=has_req,
        requirements_by_class=requirements_by_class,
    )


def canonical_marginals(dataset: SyntheticDataset) -> dict[str, object]:
    """Profile metadata + aggregates ONLY -- never generated names/ids/descriptions. This is the
    one thing scale tests may serialize/hash to prove same-seed byte-identical output."""
    return {
        "profile_id": dataset.profile.profile_id,
        "profile_version": dataset.profile.profile_version,
        "seed": dataset.profile.seed,
        "attendee_count": len(dataset.attendees),
        "raw_class_count": len(dataset.raw_class_rows),
        "deduplicated_class_count": len(dataset.deduped_class_ids),
        "requirement_count": len(dataset.requirement_rows),
        "raw_completion_marginal": dataset.raw_completion_marginal(),
        "deduped_completion_marginal": dataset.deduped_completion_marginal(),
        "has_req_marginal": dataset.has_req_marginal(),
        "flag_marginal": dataset.flag_marginal(),
        "type_marginal": dataset.type_marginal(),
        "shape_marginal": dataset.shape_marginal(),
    }
