"""The seam the ScoutingEvent session adapter implements (D22).

Neither Protocol below names a Playwright type. The acquisition feature drives a session
through these two methods only; the concrete Browser/Context/Page lifecycle is the adapter's
business, kept out of features/ and core/ so the dependency-rule architecture test can prove it.

ScheduleFetchResult/RequirementFetchResult carry the FULL upstream envelope (status + data), not
just the data rows -- process_scout today writes the complete envelope to raw/ and checks its
own status field independently of what's inside data (scout_schedule_cli.py:374,378,437,441).
A gateway that stripped the envelope down to `rows` would silently drop both behaviors.

RequirementFetchResult ALSO carries pre-validated rows and per-row schema-drift error strings --
row-level validation (ACQ-REQ-004) happens INSIDE the adapter (playwright_gateway.py, an
adapter-to-adapter import of adapters/scoutevent/schema.py, an allowed edge), never inside
features/acquisition/service.py. A feature calling a schema-validation function directly would be
"parsing an external format" in a features/ module, which the dependency rule forbids -- an
earlier draft of this plan had exactly that violation.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ScheduleFetchResult:
    attendee_id: str
    display_name: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RequirementFetchResult:
    payload: Mapping[str, Any]
    """The full envelope (status + data), unmodified -- for the raw/ dump and the status check."""

    validated_rows: tuple[Mapping[str, Any], ...]
    """Rows from `payload["data"]` that passed schema validation, already coerced/cleaned --
    the feature builds RequirementRecords from these directly, no further parsing needed."""

    row_errors: tuple[str, ...]
    """One bounded, redacted error string per row that FAILED schema validation -- the feature
    folds these into ScoutResult.errors verbatim, it never sees the raw failing row."""


class ScoutingEventSession(Protocol):
    async def fetch_schedule(
        self, qr_url: str, timeout_seconds: int, fallback_name: str
    ) -> ScheduleFetchResult: ...

    async def fetch_requirements(
        self, attendee_id: str, class_p4_id: str
    ) -> RequirementFetchResult: ...


class ScoutingEventGateway(Protocol):
    def open_session(self) -> AbstractAsyncContextManager[ScoutingEventSession]: ...
