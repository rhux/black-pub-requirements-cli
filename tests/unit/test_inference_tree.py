from __future__ import annotations

from scoutmb.core.inference.tree import build_group_tree


def test_child_links_to_registered_prefix_parent() -> None:
    tree = build_group_tree(("#8", "#8a"), ("1", "1"))
    assert tree.paths == (("8",), ("8", "a"))
    assert tree.parent_index == (None, 0)
    assert tree.children == ((1,), ())


def test_missing_parent_leaves_siblings_unlinked() -> None:
    """REQ-TREE-004: '#10a' and '#10c' with no '#10' row -- the prefix ('10',) was never
    registered, so both stay top-level and unlinked from each other."""
    tree = build_group_tree(("#10a", "#10c"), ("1", "1"))
    assert tree.parent_index == (None, None)


def test_header_stack_fallback_adopts_nearest_shallower_type_3() -> None:
    """REQ-TREE-005: a compound TYPE-3 header followed by a malformed number that matches no
    registered prefix falls back to the nearest shallower header."""
    tree = build_group_tree(("#16.Option.A", "#(y)(1)(2)"), ("3", "1"))
    assert tree.parent_index[1] == 0


def test_grandparent_chain() -> None:
    tree = build_group_tree(("#9", "#9a", "#9a1"), ("1", "1", "1"))
    assert tree.parent_index == (None, 0, 1)
    assert tree.children == ((1,), (2,), ())


def test_header_stack_pops_entries_at_or_deeper_than_a_new_sibling_header() -> None:
    """Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b
    B10.4): a shallower/equal-depth TYPE-3 header must pop the stale deeper header before
    pushing itself, or a later malformed number could wrongly fall back to the stale entry."""
    tree = build_group_tree(("1", "1a", "2"), ("3", "1", "3"))
    assert tree.paths[2] == ("2",)


def test_parent_lookup_keeps_searching_shallower_candidates() -> None:
    """Migrated from test_phase_a_gap_closure.py: a 3-level number ("1a1") whose intermediate
    level ("1a") is never its own row -- the parent-candidate loop's first try (depth 2, "1a")
    fails, so it must loop back and try depth 1 ("1") before finding a parent."""
    tree = build_group_tree(("1", "1a1"), ("1", "1"))
    assert tree.parent_index[1] == 0


def test_header_stack_fallback_keeps_searching_past_a_too_deep_entry() -> None:
    """Migrated from test_phase_a_gap_closure.py: "2a" shares no path prefix with any prior row,
    so the primary prior-path-index lookup finds nothing and falls through to the header-stack
    fallback. That fallback must itself keep searching past a too-deep header ("1a", depth 2)
    back to a shallower one ("1", depth 1)."""
    tree = build_group_tree(("1", "1a", "2a"), ("3", "3", "1"))
    assert tree.parent_index[2] == 0
