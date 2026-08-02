from __future__ import annotations

import pytest

from scoutmb.core.output_schemas import (
    SCHEMA_VERSION,
    UnsupportedSchemaVersion,
    check_schema_version,
)


def test_current_version_is_accepted() -> None:
    check_schema_version(SCHEMA_VERSION)


def test_unknown_versions_fail_closed() -> None:
    with pytest.raises(UnsupportedSchemaVersion):
        check_schema_version(SCHEMA_VERSION + 1)


def test_bool_masquerading_as_int_fails_closed() -> None:
    """True == 1 in Python, so a naive `version not in {1}` check would silently accept a
    bool. `type(version) is int` must reject it explicitly."""
    with pytest.raises(UnsupportedSchemaVersion):
        check_schema_version(True)


def test_float_masquerading_as_int_fails_closed() -> None:
    """1.0 == 1 in Python, so a naive `version not in {1}` check would silently accept a
    float. `type(version) is int` must reject it explicitly."""
    with pytest.raises(UnsupportedSchemaVersion):
        check_schema_version(1.0)  # type: ignore[arg-type]
