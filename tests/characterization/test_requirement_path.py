"""Pin current requirement_path behavior before any code moves.
Suspect cases are pinned AS-IS; a fix is a separate change with its own RED test."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from scout_schedule_cli import requirement_path


@pytest.mark.parametrize(
    ("number", "top", "path", "new_top"),
    [
        ("#3b", None, ("3", "b"), "3"),
        ("#3(b)", None, ("3", "b"), "3"),
        ("6.a.1.", None, ("6", "a", "1"), "6"),
        ("#5(c)(1)", None, ("5", "c", "1"), "5"),
        ("#1", None, ("1",), "1"),
        ("2.", None, ("2",), "2"),
        ("4", None, ("4",), "4"),
        ("#7a.", None, ("7", "a"), "7"),
        ("#8a(2)", None, ("8", "a", "2"), "8"),
        ("3.b.", None, ("3", "b"), "3"),
        ("#2.Option.A.(1)", None, ("2", "option", "a", "1"), "2"),
        ("#5.Option.D.(3)(a)", None, ("5", "option", "d", "3", "a"), "5"),
        ("#5.Option.A(1)", None, ("5", "option", "a", "1"), "5"),
        ("#5..Opt.A.(1)", None, ("5", "opt", "a", "1"), "5"),
        ("#4..Aaa.A.(1)", None, ("4", "aaa", "a", "1"), "4"),  # 18th distinct shape
        ("#(c)", "7", ("7", "c"), "7"),
        # SUSPECT: label row becomes a CHILD of the prior requirement. Unresolved.
        ("Note.", "7", ("7", "note"), "7"),
        # SUSPECT: empty number AND empty description (402 real rows). Unresolved.
        # The two rows below are ONE shape ("") in two contexts (no top / inherited top),
        # not two of the 18 shapes — they exercise the top-level-inheritance branch.
        ("", None, (), None),
        ("", "7", (), "7"),
    ],
)
def test_requirement_path_pins_current_behavior(number, top, path, new_top):
    got_path, got_top = requirement_path(number, top)
    assert got_path == path
    assert got_top == new_top


@given(st.text(max_size=40))
def test_requirement_path_never_raises(value):
    got, _ = requirement_path(value, None)
    assert isinstance(got, tuple)
