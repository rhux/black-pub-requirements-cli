"""Attendee identity and the names derived from it.

Upstream attendee ID is required identity and fails closed when absent (D3). Output identity
is a per-run UUIDv4 (D25) so a shareable filename never carries the bearer token.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


class MissingAttendeeId(RuntimeError):
    """An attendee record arrived without the ID we use as identity."""

    def __init__(self, scout_name: str = "") -> None:
        self.scout_name = scout_name
        super().__init__(f"No attendee_id for {scout_name or 'an unnamed attendee'}")


@dataclass(frozen=True, slots=True)
class AttendeeId:
    value: str

    @classmethod
    def parse(cls, raw: str, scout_name: str = "") -> AttendeeId:
        cleaned = str(raw or "").strip()
        if not cleaned:
            raise MissingAttendeeId(scout_name)
        return cls(cleaned)


@dataclass(slots=True)
class RunIdentity:
    """Assigns a UUIDv4 per attendee for one run. Stable within the run instance.

    Exactly one instance exists per run and is threaded to every collaborator that needs an
    output id. Constructing a second instance mid-run produces UUIDs that disagree with the
    rest of the run, so callers must accept an existing RunIdentity rather than default-
    constructing their own.
    """

    _by_attendee: dict[str, str] = field(default_factory=dict)

    def output_id(self, attendee: AttendeeId) -> str:
        existing = self._by_attendee.get(attendee.value)
        if existing is None:
            existing = str(uuid.uuid4())
            self._by_attendee[attendee.value] = existing
        return existing

    def snapshot(self) -> Mapping[str, str]:
        """A read-only view of the current attendee-id -> output-id map, for persisting into a
        checkpoint. Not a live view -- callers that need to observe later output_id() calls must
        re-snapshot."""
        return MappingProxyType(dict(self._by_attendee))

    def hydrate(self, existing: Mapping[str, str]) -> None:
        """Seed this instance's map from a prior run's snapshot (e.g. a loaded checkpoint), so
        an attendee this run already resolved on a previous process gets the SAME output_id
        again rather than a fresh one. Only call this before any output_id() calls on this
        instance -- hydrating after would not retroactively change UUIDs already handed out."""
        self._by_attendee.update(existing)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "unknown-scout"


def attendee_filename_stem(scout_name: str, output_id: str) -> str:
    """Readable, collision-free filename stem: name slug + the FULL per-run output UUID
    (hyphens stripped). The full UUID — never a truncation — guarantees distinct attendees
    get distinct filenames. Never the raw attendee_id (a bearer token that must not appear
    in a shareable filename)."""
    return f"{safe_slug(scout_name)}-{str(output_id).replace('-', '')}"
