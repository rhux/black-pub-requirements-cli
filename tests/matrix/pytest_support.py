from __future__ import annotations

from typing import Protocol, TypeVar

import pytest
from _pytest.mark.structures import ParameterSet

from tests.matrix.model import CaseMetadata, Classification


class HasMetadata(Protocol):
    meta: CaseMetadata


CaseT = TypeVar("CaseT", bound=HasMetadata)


def execution_params(cases: tuple[CaseT, ...]) -> list[ParameterSet]:
    return [
        pytest.param(
            case,
            context_id,
            id=f"{case.meta.case_id}[{context_id}]",
            marks=pytest.mark.matrix_case(
                case_id=case.meta.case_id,
                context_id=context_id,
                lane=case.meta.lane.value,
            ),
        )
        for case in cases
        for context_id in case.meta.contexts
        if case.meta.classification is not Classification.NEW_ACCEPTANCE
    ]
