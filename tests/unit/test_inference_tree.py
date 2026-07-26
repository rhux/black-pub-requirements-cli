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
