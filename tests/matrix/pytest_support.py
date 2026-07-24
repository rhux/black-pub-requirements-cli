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


def assert_platform_domain_registry_valid() -> None:
    """Shared body for the three byte-for-byte-identical ``Domain.PLATFORM`` registry checks
    in ``test_platform_matrix.py``/``test_desktop_matrix.py``/``test_bootstrap_matrix.py``:
    ``Domain.PLATFORM`` is shared by the ``PLAT-*``/``DESK-*``/``BOOT-*`` catalogs (see those
    modules' docstrings for the documented domain-reuse reasoning), so this domain-scoped
    registry check must pull all three catalogs in together. Each of the three test files keeps
    its own thin ``test_*_registry_is_structurally_valid`` wrapper around this helper so the
    catalog each file owns stays covered even if one of the other two files is ever deleted.
    """
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.bootstrap_cases import ALL_BOOTSTRAP_METADATA
    from tests.matrix.cases.desktop_cases import ALL_DESKTOP_METADATA
    from tests.matrix.cases.platform_cases import ALL_PLATFORM_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    platform_axes = [axis for axis in AXES if axis.domain is Domain.PLATFORM]
    platform_boundaries = [b for b in BOUNDARIES if b.domain is Domain.PLATFORM]

    errors = validate_registry(
        ALL_PLATFORM_METADATA + ALL_DESKTOP_METADATA + ALL_BOOTSTRAP_METADATA,
        platform_axes,
        platform_boundaries,
        [],
        list(POLICIES),
    )
    assert errors == ()
