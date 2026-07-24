"""Typed matrix execution of the platform characterization catalog (Task 21).

Every ``PLAT-*`` case declares a single ``slug`` context; ``execution_params`` expands it. The
runner drives the REAL ``scout_schedule_cli.safe_slug`` (never mocked) and independently
recomputes ``expected_components`` from ``raw`` via ``pathlib.PureWindowsPath`` /
``pathlib.PurePosixPath`` (pure, no I/O, no real OS involved) -- never by calling the sanitizer
under test to produce its own expected value.

No test writes outside ``tmp_path`` and this module performs no real file or network I/O; it
never monkeypatches ``sys.platform``.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path, PureWindowsPath

import pytest
from tests.matrix.cases.platform_cases import (
    PLATFORM_CASES,
    PLATFORM_CASES_MAC,
    PLATFORM_CASES_WIN,
    PlatformCase,
)
from tests.matrix.pytest_support import execution_params


class LegacyPlatformRunner:
    """Runner[PlatformCase, object] over the real ``scout_schedule_cli.safe_slug`` seam."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: PlatformCase, *, root: Path) -> object:
        handler = getattr(self, f"_ctx_{self.context_id}")
        return handler(case)

    def _ctx_slug(self, case: PlatformCase) -> tuple[object, ...]:
        import scout_schedule_cli as legacy

        collision_key = legacy.safe_slug(case.raw)

        # Pure, stdlib-only recomputation of expected_components -- never the function under
        # test. Windows-axis cases use PureWindowsPath (an offline path-string parser, no I/O,
        # no dependency on the host OS). macOS-axis cases NFC-normalize first (per the Task 21
        # contract: "macOS cases use unicodedata.normalize('NFC', value)") then split on '/'.
        if case in PLATFORM_CASES_WIN:
            components = PureWindowsPath(case.raw).parts
        else:
            assert case in PLATFORM_CASES_MAC
            normalized = unicodedata.normalize("NFC", case.raw)
            components = tuple(part for part in normalized.split("/") if part)

        return (components, collision_key)


@pytest.mark.parametrize(("case", "context_id"), execution_params(PLATFORM_CASES))
def test_platform_execution(case: PlatformCase, context_id: str, tmp_path: Path) -> None:
    observed = LegacyPlatformRunner(context_id).run(case, root=tmp_path)
    assert observed == (case.expected_components, case.expected_collision_key)


def test_platform_registry_is_structurally_valid() -> None:
    # Domain.PLATFORM is shared by this module's PLAT-* cases and Task 21's final-slice
    # DESK-*/BOOT-* cases (tests/matrix/cases/desktop_cases.py, bootstrap_cases.py -- see their
    # module docstrings for the documented domain-reuse reasoning), so this domain-scoped
    # registry check must pull all three catalogs in together, exactly as
    # test_interface_matrix.py does for its own multi-catalog INTERFACE/PDF domain check.
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.cases.bootstrap_cases import ALL_BOOTSTRAP_METADATA
    from tests.matrix.cases.desktop_cases import ALL_DESKTOP_METADATA
    from tests.matrix.cases.platform_cases import ALL_PLATFORM_METADATA
    from tests.matrix.model import Domain
    from tests.matrix.policies import POLICIES
    from tests.matrix.registry import validate_registry

    plat_axes = [axis for axis in AXES if axis.domain is Domain.PLATFORM]
    plat_boundaries = [b for b in BOUNDARIES if b.domain is Domain.PLATFORM]

    errors = validate_registry(
        ALL_PLATFORM_METADATA + ALL_DESKTOP_METADATA + ALL_BOOTSTRAP_METADATA,
        plat_axes,
        plat_boundaries,
        [],
        list(POLICIES),
    )
    assert errors == ()
