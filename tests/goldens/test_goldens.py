from __future__ import annotations

import json
from pathlib import Path

GOLDENS = Path(__file__).parent


def test_current_implementation_matches_the_active_golden() -> None:
    """Compare the live render against whichever projection is currently shipped.

    Until Task 23 that is V1; after it, V2. Pinning this test to `v1_operational.json` forever
    would make it regenerate-and-compare against the wrong file the moment the tiering lands,
    turning the whole suite red for a reason that has nothing to do with a regression.
    """
    from tools.gen_golden import build

    active = (
        "v2_shareable.json" if (GOLDENS / "v2_shareable.json").exists() else "v1_operational.json"
    )
    stored = json.loads((GOLDENS / active).read_text(encoding="utf-8"))
    live = build(stored["kind"])
    assert live == stored, (
        f"{active} drifted. If intended, regenerate with "
        f"`uv run python tools/gen_golden.py {stored['kind']}` and review the diff."
    )


def test_v1_is_immutable_once_written() -> None:
    """V1 records the pre-move operational shape. It is never regenerated after Task 19 --
    the V1->V2 diff assertion depends on it being a fixed reference point."""
    stored = json.loads((GOLDENS / "v1_operational.json").read_text(encoding="utf-8"))
    assert stored["kind"] == "v1"
    assert stored["report_data"]["classes"], "V1 was generated from an empty fixture"


def test_same_named_attendees_stay_separate_in_the_golden() -> None:
    """The fixture's two Jordan Samples must never collapse into one entry."""
    stored = json.loads((GOLDENS / "v1_operational.json").read_text(encoding="utf-8"))
    scouts = [s for s in stored["report_data"]["scouts"] if s["name"] == "Jordan Sample"]
    assert len(scouts) == 2, scouts
    assert scouts[0] != scouts[1]


_TRANSFORMED = ("scouts", "classes", "requirements", "errors")


def test_v1_to_v2_diff_is_exactly_the_declared_substitution() -> None:
    """Catches a move-induced change hiding inside an intentional one.

    The only permitted difference between the two goldens is attendee_id -> output_id in the
    four transformed collections. Any other changed key, value, type, or ordering fails.
    """
    v1 = json.loads((GOLDENS / "v1_operational.json").read_text(encoding="utf-8"))
    v2 = json.loads((GOLDENS / "v2_shareable.json").read_text(encoding="utf-8"))

    assert v1["emails"] == v2["emails"], (
        "email bodies already carried no identity; they must not change"
    )

    top_v1 = {k: v for k, v in v1["report_data"].items() if k not in _TRANSFORMED}
    top_v2 = {k: v for k, v in v2["report_data"].items() if k not in _TRANSFORMED}
    assert top_v1 == top_v2, "the top-level object is unchanged (ART-SCHEMA-006)"

    for collection in _TRANSFORMED:
        rows_v1 = v1["report_data"][collection]
        rows_v2 = v2["report_data"][collection]
        assert len(rows_v1) == len(rows_v2), collection
        for before, after in zip(rows_v1, rows_v2, strict=True):
            expected_keys = ["output_id" if key == "attendee_id" else key for key in before]
            assert list(after) == expected_keys, f"{collection}: key set or order changed"
            for key in before:
                if key == "attendee_id":
                    continue
                assert after[key] == before[key], f"{collection}.{key} changed with the projection"
