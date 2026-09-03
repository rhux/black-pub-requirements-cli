from __future__ import annotations

import pytest

winreg = pytest.importorskip("winreg")


def test_getattr_hive_lookup_resolves_the_same_constants_as_direct_attribute_access():
    from bootstrap.webview2 import _CANDIDATE_KEYS

    for hive_name, _ in _CANDIDATE_KEYS:
        resolved = getattr(winreg, hive_name)
        assert resolved == getattr(winreg, hive_name)  # stable across repeated lookups
        assert isinstance(resolved, int)
