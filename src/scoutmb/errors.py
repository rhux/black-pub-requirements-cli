"""Typed errors for scoutmb."""

from __future__ import annotations


class ScoutmbError(Exception):
    """Base class for every error this package raises."""


class ExternalNetworkBlocked(ScoutmbError):
    def __init__(self, host: str) -> None:
        self.host = host
        super().__init__(
            f"Egress to {host!r} is blocked. Set SCOUTMB_ALLOW_LIVE_SERVICE and use the "
            f"'live_service' marker to opt in."
        )
