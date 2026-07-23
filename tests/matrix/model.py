from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Generic, Protocol, TypeVar


class Classification(StrEnum):
    PRESERVE = "preserve"
    INTENTIONAL_CHANGE = "intentional-change"
    NEW_ACCEPTANCE = "new-acceptance"


class EvidenceKind(StrEnum):
    CORPUS_AGGREGATE = "corpus-aggregate"
    CURRENT_BRANCH = "current-branch"
    PUBLIC_CONTRACT = "public-contract"
    PROPERTY_BOUNDARY = "property-boundary"


class Domain(StrEnum):
    CORPUS = "corpus"
    INPUT = "input"
    PDF = "pdf"
    ACQUISITION = "acquisition"
    REQUIREMENT = "requirement"
    ARTIFACT = "artifact"
    INTERFACE = "interface"
    PLATFORM = "platform"
    SCALE = "scale"
    FLOW = "flow"


class Lane(StrEnum):
    DEFAULT = "default"
    BROWSER = "browser"
    AUTHENTIC = "authentic"


class SurfaceClass(StrEnum):
    INPUT_PRIVATE = "input-private"
    ADAPTER_PRIVATE = "adapter-private"
    OPERATIONAL_PRIVATE = "operational-private"
    AUDIENCE_SHAREABLE = "audience-shareable"
    LOCAL_UI = "local-ui"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True, order=True)
class ExecutionKey:
    case_id: str
    context_id: str


@dataclass(frozen=True, slots=True)
class CaseMetadata:
    case_id: str
    axis_id: str
    member: str
    domain: Domain
    classification: Classification
    evidence: EvidenceKind
    rationale: str
    contexts: tuple[str, ...]
    lane: Lane = Lane.DEFAULT
    evidence_reference: str = ""
    interaction_ids: frozenset[str] = frozenset()
    surface_id: str | None = None
    target_owner: str | None = None
    target_observation: str | None = None

    def execution_keys(self) -> tuple[ExecutionKey, ...]:
        if self.classification is Classification.NEW_ACCEPTANCE:
            return ()
        return tuple(ExecutionKey(self.case_id, context) for context in self.contexts)


InputT = TypeVar("InputT")
ObservationT = TypeVar("ObservationT")


class Runner(Protocol, Generic[InputT, ObservationT]):
    def run(self, value: InputT, *, root: Path) -> ObservationT: ...
