"""Attendee ingestion orchestration.

The feature owns POLICY -- which source to use, what counts as an attendee, what a duplicate
is, and what an empty result means. Adapters own PARSING. Keeping the split here is what lets
a core-only install import this module without PyMuPDF.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scoutmb.core.models import ScoutInput
from scoutmb.errors import ScoutmbError
from scoutmb.ports.attendee_source import AttendeeSource

QR_URL_PREFIX = "https://scoutingevent.com/mobile/"
ADULT_TYPES = frozenset({"adult", "part-time adult"})


class NoSupportedSource(ScoutmbError):
    """No configured source claimed this file."""


@dataclass(frozen=True, slots=True)
class IngestService:
    sources: Sequence[AttendeeSource] = field(default_factory=tuple)
    include_adults: bool = False

    def load(self, path: Path) -> list[ScoutInput]:
        raw = self._parse(path)

        selected: list[ScoutInput] = []
        seen: set[str] = set()
        for scout in raw:
            # New instances, not in-place strip: the adapter's objects are not ours to mutate,
            # and the record shape is frozen in a later slice.
            normalized = ScoutInput(
                name=scout.name.strip(),
                url=scout.url.strip(),
                registrant_type=scout.registrant_type.strip(),
            )
            if not normalized.url.startswith(QR_URL_PREFIX):
                continue
            if not self.include_adults and normalized.registrant_type.lower() in ADULT_TYPES:
                continue
            if normalized.url in seen:
                continue
            seen.add(normalized.url)
            selected.append(normalized)

        if not selected:
            # Message is byte-identical to the legacy raise; IN-ERROR-* pins it.
            raise ValueError(f"No ScoutingEvent QR URLs found in {path}")
        return selected

    def _parse(self, path: Path) -> list[ScoutInput]:
        for source in self.sources:
            if source.supports(path):
                return source.load(path)
        raise NoSupportedSource(f"No configured source can read {path.suffix or path.name!r}")
