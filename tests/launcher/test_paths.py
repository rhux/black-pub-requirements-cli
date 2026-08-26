from __future__ import annotations

import pytest
from bootstrap import paths


def test_resolve_root_raises_diagnosable_error_without_override_or_localappdata(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SCOUTMB_BOOTSTRAP_ROOT", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(RuntimeError, match="LOCALAPPDATA"):
        paths.resolve_root()
