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
