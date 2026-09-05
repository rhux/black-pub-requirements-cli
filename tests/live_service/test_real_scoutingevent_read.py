from __future__ import annotations

import os
import urllib.request

import pytest

from scoutmb.network_policy import assert_egress_allowed

pytestmark = pytest.mark.live_service


@pytest.mark.skipif(
    not os.environ.get("SCOUTMB_ALLOW_LIVE_SERVICE"),
    reason="requires SCOUTMB_ALLOW_LIVE_SERVICE=1 -- manual, read-only, opt-in only",
)
def test_real_scoutingevent_site_responds_to_a_read_only_probe():
    """The ONE test in this suite allowed to touch the real service. Read-only: fetches the
    public, non-authenticated homepage and asserts it responds -- never a real QR URL, never
    any write, never real attendee data. Run manually:
    SCOUTMB_ALLOW_LIVE_SERVICE=1 uv run pytest -m live_service"""
    assert_egress_allowed("scoutingevent.com")
    with urllib.request.urlopen("https://scoutingevent.com/", timeout=10) as response:  # noqa: S310
        assert response.status == 200
