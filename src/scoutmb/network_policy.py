"""Application-level egress guard.

pytest-socket blocks Python sockets in tests, but a Playwright browser subprocess
is a separate process it cannot see. Feature code that is about to reach the network
calls assert_egress_allowed so the intent is guarded in the application too, not only
in the test harness.
"""

from __future__ import annotations

import os

from scoutmb.errors import ExternalNetworkBlocked

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_LIVE_OPT_IN = "SCOUTMB_ALLOW_LIVE_SERVICE"


def assert_egress_allowed(host: str) -> None:
    """Raise unless `host` is loopback or the two-part live opt-in is set."""
    if host in _LOOPBACK:
        return
    if os.environ.get(_LIVE_OPT_IN):
        return
    raise ExternalNetworkBlocked(host)
