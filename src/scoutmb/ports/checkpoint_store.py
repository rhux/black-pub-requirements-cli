"""The seam a checkpoint adapter implements (ACQ-RESUME). One real implementation (an atomic
JSON file) and this Protocol, matching every other port in this codebase -- not the generic
ports/storage.py the Phase B spec declines to create, since this is fixed to one schema rather
than a general filesystem abstraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from scoutmb.errors import ScoutmbError

CHECKPOINT_VERSION = 1


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """frozen=True freezes the FIELD REFERENCE, not a mutable dict sitting behind it -- so
    __post_init__ copies output_ids/completed_results into MappingProxyTypes, making the
    exposed mappings genuine read-only views rather than typed-but-mutable dicts a caller could
    still corrupt through their own retained reference to the mapping they passed in.

    completed_results holds one scout_result_to_row-shaped mapping per completed scout's URL
    (the same key space as completed_urls) -- Task B5.5's run_batch reads this back via
    scout_result_from_row so a resumed run's report still includes scouts finished on a prior
    process, not just the ones this process newly handles. Defaulted to {} so checkpoint files
    saved before this field existed keep loading (see AtomicFileCheckpointStore.load's
    backward-compatible .get)."""

    version: int
    completed_urls: tuple[str, ...]
    output_ids: Mapping[str, str] = field(default_factory=dict)
    completed_results: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_ids", MappingProxyType(dict(self.output_ids)))
        # TWO levels of MappingProxyType, not one -- output_ids' values are plain strings
        # (already immutable), but completed_results' values are themselves dicts. Wrapping
        # only the OUTER completed_results mapping (as an earlier draft did) leaves each row
        # dict mutable through the exposed mapping's own values -- checkpoint.completed_results
        # ["url"]["name"] = "x" would silently succeed, contradicting this class's own
        # "genuine read-only view" claim. Freezing each row too closes that gap.
        object.__setattr__(
            self,
            "completed_results",
            MappingProxyType(
                {url: MappingProxyType(dict(row)) for url, row in self.completed_results.items()}
            ),
        )


class CorruptCheckpoint(ScoutmbError):
    """A checkpoint file exists but cannot be trusted: unreadable, wrong-shaped, or an
    unsupported version. Resuming from it is refused rather than guessed at. Subclasses
    ScoutmbError like every other exception this package raises (errors.py:6)."""


class CheckpointStore(Protocol):
    def load(self) -> Checkpoint | None: ...
    def save(self, checkpoint: Checkpoint) -> None: ...
