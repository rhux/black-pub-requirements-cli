"""No-op-by-default event recording (D5). Follows ports/clock.py's Protocol-per-collaborator
convention: one minimal method, injected, never a bag of unrelated capabilities.

Event attributes are validated against a closed vocabulary that forbids anything that could
identify a real person or their data -- names, paths, URLs, IDs, tokens -- since QR URLs and
attendee IDs act as bearer access tokens for real scouts' data (see CLAUDE.md's privacy notes).
"""

from __future__ import annotations

import re
from typing import Protocol

_FORBIDDEN_KEYS = {"name", "path", "url", "qr_url", "attendee_id", "token"}
_PATH_OR_URL_LIKE = re.compile(r"^/|^[A-Za-z]:\\|^https?://")


class InvalidObservabilityEvent(ValueError):
    pass


class ObservabilityPort(Protocol):
    def record(self, event: str, **attributes: str) -> None: ...


def validate_event(event: str, attributes: dict[str, str]) -> None:  # noqa: ARG001 -- matches ObservabilityPort.record's shape
    for key, value in attributes.items():
        if key in _FORBIDDEN_KEYS:
            raise InvalidObservabilityEvent(f"attribute key {key!r} is forbidden")
        if _PATH_OR_URL_LIKE.match(value):
            raise InvalidObservabilityEvent(f"attribute {key!r} looks like a path/URL: {value!r}")
