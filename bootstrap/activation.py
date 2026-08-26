"""The activation tuple: what current.json records about the currently-active release, and the
compatibility check a candidate release must pass before it can become current.json. Kept
separate from release_manifest.py -- a ReleaseManifest describes a BUILT release (what it can
do); an ActivationTuple describes the INSTALLED-AND-ACTIVE state (what is running now)."""

from __future__ import annotations

from dataclasses import dataclass

from bootstrap.release_manifest import ReleaseManifest


@dataclass(frozen=True, slots=True)
class ActivationTuple:
    release_version: str
    state_generation: int
    capability_manifest_digest: str

    def to_json(self) -> dict[str, object]:
        return {
            "release_version": self.release_version,
            "state_generation": self.state_generation,
            "capability_manifest_digest": self.capability_manifest_digest,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> ActivationTuple:
        return cls(
            release_version=str(data["release_version"]),
            state_generation=int(data["state_generation"]),  # type: ignore[arg-type]
            capability_manifest_digest=str(data["capability_manifest_digest"]),
        )


def validate_activation(candidate: ReleaseManifest, installed_state_generation: int) -> bool:
    """A candidate release may activate only if it can read the durable state that is already
    on disk -- fails closed (returns False) for both an unknown-newer generation the candidate
    predates, and a too-old generation the candidate has since dropped support for."""
    return candidate.state_schema_min <= installed_state_generation <= candidate.state_schema_max
