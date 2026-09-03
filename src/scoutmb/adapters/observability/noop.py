"""NoopObservability -- the only ObservabilityPort implementation shipped in this slice.
Deliberately does nothing but validate; no disk write, no network, ever."""

from __future__ import annotations

from scoutmb.ports.observability import validate_event


class NoopObservability:
    def record(self, event: str, **attributes: str) -> None:
        validate_event(event, attributes)
