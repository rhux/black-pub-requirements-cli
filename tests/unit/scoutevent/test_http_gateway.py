from __future__ import annotations

import pytest

from scoutmb.adapters.scoutevent.http_gateway import fetch_requirement_payload
from scoutmb.errors import ExternalNetworkBlocked


@pytest.mark.matrix_case(case_id="NET-WIRE-001", context_id="net-wire", lane="default")
async def test_egress_check_runs_before_evaluate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOUTMB_ALLOW_LIVE_SERVICE", raising=False)

    class _ExplodingPage:
        async def evaluate(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("evaluate() must not be called when egress is blocked")

    with pytest.raises(ExternalNetworkBlocked):
        await fetch_requirement_payload(_ExplodingPage(), "A1", "C1")


async def test_full_envelope_is_returned_unmodified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    import json as _json

    class _FakePage:
        async def evaluate(self, *args: object, **kwargs: object) -> dict[str, object]:
            payload = {"status": {"status": 1}, "data": [{"MDM_LKP_BADGE_REQ_ID": "1"}]}
            return {"ok": True, "status": 200, "text": _json.dumps(payload)}

    result = await fetch_requirement_payload(_FakePage(), "A1", "C1")
    assert result == {"status": {"status": 1}, "data": [{"MDM_LKP_BADGE_REQ_ID": "1"}]}
