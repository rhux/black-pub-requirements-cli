from __future__ import annotations

from bootstrap.config import SMOKE_TEST_IMPORTS


def test_smoke_test_imports_includes_the_app_package_itself() -> None:
    assert "scoutmb" in SMOKE_TEST_IMPORTS
