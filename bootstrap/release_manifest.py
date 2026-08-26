"""What one built release declares about itself: version, the Python ABI it was built for, its
pinned-requirements hash, and the durable-state schema window it can read. bootstrap/ stays
stdlib-only and imports no app code -- version comes from pyproject.toml via tomllib, never
`import scoutmb` (that would require the release's own environment to already be provisioned,
which is exactly what hasn't happened yet when this manifest is built)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from bootstrap.config import DURABLE_STATE_SCHEMA_VERSION
from bootstrap.marker import compute_requirements_hash


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    version: str
    python_abi: str
    requirements_hash: str
    state_schema_min: int
    state_schema_max: int

    def to_json(self) -> dict[str, object]:
        return {
            "version": self.version,
            "python_abi": self.python_abi,
            "requirements_hash": self.requirements_hash,
            "state_schema_min": self.state_schema_min,
            "state_schema_max": self.state_schema_max,
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> ReleaseManifest:
        return cls(
            version=str(data["version"]),
            python_abi=str(data["python_abi"]),
            requirements_hash=str(data["requirements_hash"]),
            state_schema_min=int(data["state_schema_min"]),  # type: ignore[arg-type]
            state_schema_max=int(data["state_schema_max"]),  # type: ignore[arg-type]
        )


def build_release_manifest(source_root: Path, requirements_path: Path) -> ReleaseManifest:
    pyproject = tomllib.loads((source_root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(pyproject["project"]["version"])
    return ReleaseManifest(
        version=version,
        python_abi="cp312",
        requirements_hash=compute_requirements_hash(requirements_path),
        state_schema_min=max(1, DURABLE_STATE_SCHEMA_VERSION - 1),
        state_schema_max=DURABLE_STATE_SCHEMA_VERSION,
    )
