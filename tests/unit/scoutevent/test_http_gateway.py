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


# Migrated from tests/characterization/test_phase_a_gap_closure.py (retired in Slice 2b B10.4):
# the two error branches after the in-page fetch() resolves.


class _StaticResultPage:
    def __init__(self, result: dict[str, object]) -> None:
        self._result = result

    async def evaluate(self, script: str, arg: object) -> dict[str, object]:
        return self._result


async def test_raises_on_non_ok_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    page = _StaticResultPage({"ok": False, "status": 500, "text": ""})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        await fetch_requirement_payload(page, "1", "2")


async def test_raises_on_non_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCOUTMB_ALLOW_LIVE_SERVICE", "1")
    page = _StaticResultPage({"ok": True, "status": 200, "text": "<html>not json</html>"})
    with pytest.raises(RuntimeError, match="was not JSON"):
        await fetch_requirement_payload(page, "1", "2")
