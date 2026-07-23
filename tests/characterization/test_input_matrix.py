"""Typed matrix execution of the legacy input-loader characterization catalog (Task 17).

Each ``IN-*`` case declares its own execution contexts; ``execution_params`` expands them.
The runner materializes a real input file via the deterministic builders and calls the REAL
``load_inputs`` / ``load_csv`` / ``load_xlsx`` / ``load_json`` / ``load_text`` (or, for
``IN-IMPORT``, an isolated subprocess import probe). Nothing here mocks the loaders -- only
the file-system inputs are synthetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tests.factories.inputs import (
    write_csv_input,
    write_json_input,
    write_text_input,
    write_xlsx_input,
)
from tests.harnesses.subprocess import run_import_probe
from tests.matrix.cases.input_cases import INPUT_CASES, InputObservation, InputSpec
from tests.matrix.model import Domain
from tests.matrix.pytest_support import execution_params

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_LEGACY_MODULE_PATH = _REPO_ROOT / "scout_schedule_cli.py"

# Top-level module roots blocked in each import profile. ``base`` blocks nothing; the others
# withhold the optional stacks so we can observe what scout_schedule_cli truly requires.
_IMPORT_PROFILE_BLOCKS: dict[str, tuple[str, ...]] = {
    "base": (),
    "pdf": ("fitz", "cv2"),
    "acquisition": ("playwright",),
    "all": ("playwright", "fitz", "cv2", "openpyxl"),
}


class LegacyInputRunner:
    """Runner[InputSpec, InputObservation] over the real legacy loaders."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, value: InputSpec, *, root: Path) -> InputObservation:
        if self.context_id == "subprocess":
            return self._run_import(value)
        path = self._materialize(value, root)
        return self._invoke(value, path)

    def _materialize(self, value: InputSpec, root: Path) -> Path:
        if self.context_id == "csv":
            return write_csv_input(root / "input.csv", value.headers, value.rows)
        if self.context_id == "xlsx":
            sheets = value.sheets or (("Sheet", value.headers, value.rows),)
            return write_xlsx_input(root / "input.xlsx", sheets)
        if self.context_id == "json":
            return write_json_input(root / "input.json", value.json_value)
        if self.context_id == "text":
            return write_text_input(root / "input.txt", value.text_lines)
        raise ValueError(f"unsupported file context: {self.context_id}")

    def _invoke(self, value: InputSpec, path: Path) -> InputObservation:
        import scout_schedule_cli as legacy

        try:
            if value.entry == "load_inputs":
                result = legacy.load_inputs(path, value.sheet_arg, value.include_adults)
            elif value.entry == "load_csv":
                result = legacy.load_csv(path)
            elif value.entry == "load_xlsx":
                result = legacy.load_xlsx(path, value.sheet_arg)
            elif value.entry == "load_json":
                result = legacy.load_json(path)
            elif value.entry == "load_text":
                result = legacy.load_text(path)
            else:
                raise ValueError(f"unsupported entry: {value.entry}")
        except Exception as exc:  # characterizing the real exception contract
            message = str(exc).replace(str(path), "<input>")
            return InputObservation(exception_type=type(exc).__name__, message=message)

        records = tuple(
            (scout.name, scout.url, scout.registrant_type) for scout in result
        )
        return InputObservation(records=records)

    def _run_import(self, value: InputSpec) -> InputObservation:
        blocked = _IMPORT_PROFILE_BLOCKS[value.profile]
        probe = run_import_probe(value.profile, _LEGACY_MODULE_PATH, blocked)
        imported = ",".join(probe.imported_modules)
        message = (
            f"profile={probe.profile} returncode={probe.returncode} imported={imported}"
        )
        return InputObservation(exception_type=probe.exception_type, message=message)


@pytest.mark.parametrize(("case", "context_id"), execution_params(INPUT_CASES))
def test_input_case(case, context_id: str, tmp_path: Path) -> None:
    observed = LegacyInputRunner(context_id).run(case.input, root=tmp_path)
    assert observed == case.expected_legacy


def test_input_registry_is_structurally_valid() -> None:
    # Validate the input catalog in isolation. ALL_CASES is intentionally not wired into the
    # lane-accounting registry until Task 22, so we assemble the input-domain slice directly.
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.registry import validate_registry

    input_metas = [case.meta for case in INPUT_CASES]
    input_axes = [axis for axis in AXES if axis.domain is Domain.INPUT]
    input_boundaries = [b for b in BOUNDARIES if b.domain is Domain.INPUT]

    errors = validate_registry(input_metas, input_axes, input_boundaries, [], [])
    assert errors == ()
