"""The seam ingest adapters implement: parse a file into raw attendee inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from scoutmb.core.models import ScoutInput


class AttendeeSource(Protocol):
    def supports(self, path: Path) -> bool: ...
    def load(self, path: Path) -> list[ScoutInput]: ...
