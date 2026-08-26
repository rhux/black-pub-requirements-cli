from __future__ import annotations

from bootstrap.activation import validate_activation
from bootstrap.release_manifest import ReleaseManifest


def _manifest(version: str, schema_min: int, schema_max: int) -> ReleaseManifest:
    return ReleaseManifest(
        version=version,
        python_abi="cp312",
        requirements_hash="deadbeef",
        state_schema_min=schema_min,
        state_schema_max=schema_max,
    )


def test_n_and_n_minus_one_matrix() -> None:
    release_n = _manifest("0.2.0", schema_min=1, schema_max=2)
    release_n_minus_1 = _manifest("0.1.0", schema_min=1, schema_max=1)

    # Both releases can activate against a state generation of 1 -- the N/N-1 overlap window.
    assert validate_activation(release_n, installed_state_generation=1) is True
    assert validate_activation(release_n_minus_1, installed_state_generation=1) is True
    # Only release N can activate against generation 2 (a schema release N-1 predates).
    assert validate_activation(release_n, installed_state_generation=2) is True
    assert validate_activation(release_n_minus_1, installed_state_generation=2) is False


def test_unknown_newer_schema_fails_before_write() -> None:
    release = _manifest("0.1.0", schema_min=1, schema_max=1)

    assert validate_activation(release, installed_state_generation=99) is False
