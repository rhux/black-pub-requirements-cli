from __future__ import annotations

import json

from bootstrap.activation import ActivationTuple


def test_all_components_validated_together() -> None:
    tuple_ = ActivationTuple(
        release_version="0.2.0",
        state_generation=2,
        capability_manifest_digest="abc123",
    )

    round_tripped = ActivationTuple.from_json(json.loads(json.dumps(tuple_.to_json())))

    assert round_tripped == tuple_
