"""Deterministic variable-scale synthetic data profile primitives (Task 22, Slice 1b Phase A).

Locked-shape contracts: ``ScaleProfile``, ``allocate``, ``synthetic_uuid4``,
``EvidenceKindForProfile``, ``UnsupportedSyntheticCorrelation``, and ``require_supported`` are
specified exactly by the Task 22 plan -- do not deviate from their shapes. ``pairing_order`` (not
individually named in the plan's code block, but described in prose) implements "Pair independent
marginals by sorting row indices with sha256(...)" and is the one additional building block every
generator in ``tests/factories/scale.py`` shares.

This module performs no I/O, imports no legacy application code, and generates only deterministic
data derived from ``(profile_version, seed, ...)`` -- never anything read from ``raw_data/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from hashlib import sha256
from uuid import UUID


def allocate(total: int, weighted_keys: tuple[tuple[str, int], ...]) -> dict[str, int]:
    """Largest-remainder allocation of ``total`` across ``weighted_keys`` (locked shape)."""
    denominator = sum(weight for _, weight in weighted_keys)
    exact = [(key, Fraction(total * weight, denominator)) for key, weight in weighted_keys]
    result = {key: value.numerator // value.denominator for key, value in exact}
    remainder = total - sum(result.values())
    ranked = sorted(
        enumerate(exact),
        key=lambda item: (
            -(item[1][1] - result[item[1][0]]),
            item[0],
        ),
    )
    for _, (key, _) in ranked[:remainder]:
        result[key] += 1
    return result


def synthetic_uuid4(profile_version: int, seed: str, attendee_index: int) -> UUID:
    """A deterministic, RFC-4122-shaped (variant + version-4 bits) TEST identity -- not a claim
    that real production UUIDv4 generation is deterministic."""
    raw = bytearray(
        sha256(f"{profile_version}:{seed}:attendee:{attendee_index}".encode()).digest()[:16]
    )
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(raw))


def pairing_order(profile_version: int, seed: str, axis_id: str, row_count: int) -> tuple[int, ...]:
    """Stable-across-Python-versions row order for pairing an independent marginal onto
    ``row_count`` rows: ``sorted(range(row_count), key=sha256(f"{version}:{seed}:{axis}:{i}"))``.
    Never copies a private row or string -- operates purely on integer row indices."""
    indices = list(range(row_count))
    indices.sort(
        key=lambda i: sha256(f"{profile_version}:{seed}:{axis_id}:{i}".encode()).digest()
    )
    return tuple(indices)


class EvidenceKindForProfile(StrEnum):
    MARGINAL = "marginal"
    TOPOLOGY = "topology"
    ORDERING = "ordering"
    REQUEST_COUNT = "request-count"
    CORRELATION = "correlation"


@dataclass(frozen=True, slots=True)
class ScaleProfile:
    profile_id: str
    schema_version: int
    profile_version: int
    seed: str
    attendee_count: int
    raw_class_count: int
    deduplicated_class_count: int
    requirement_count: int
    pairing_is_synthetic: bool = True


class UnsupportedSyntheticCorrelation(RuntimeError):
    pass


def require_supported(profile: ScaleProfile, evidence: EvidenceKindForProfile) -> None:
    if evidence is EvidenceKindForProfile.CORRELATION:
        raise UnsupportedSyntheticCorrelation(profile.profile_id)
