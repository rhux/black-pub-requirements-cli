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
