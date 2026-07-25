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


class CapabilityUnavailable(ScoutmbError):
    """An optional capability was requested but its distributions are not installed.

    Raised instead of letting a bare ImportError traceback escape, so the message can name
    the remedy. The message text is user-facing.
    """

    def __init__(self, *, capability: str, distributions: tuple[str, ...], extra: str) -> None:
        self.capability = capability
        self.distributions = distributions
        self.extra = extra
        needed = ", ".join(distributions)
        super().__init__(
            f"The {capability} capability needs {needed}, which is not installed. "
            f"Install it with: pip install 'scoutmb[{extra}]'"
        )
