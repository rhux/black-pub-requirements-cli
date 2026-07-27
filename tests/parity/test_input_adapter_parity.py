"""Package input loaders over the SAME cases the legacy runner uses.

Neither runner is the other's oracle: tests/matrix/cases/input_cases.py holds hand-computed
InputObservation values and both sides are measured against them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.factories.inputs import (
    write_csv_input,
    write_json_input,
    write_text_input,
    write_xlsx_input,
)
from tests.matrix.cases.input_cases import INPUT_CASES, InputObservation, InputSpec
from tests.matrix.pytest_support import execution_params

_FILE_CONTEXTS = {"csv", "xlsx", "json", "text"}


def _materialize(spec: InputSpec, context_id: str, root: Path) -> Path:
    if context_id == "csv":
        return write_csv_input(root / "input.csv", spec.headers, spec.rows)
    if context_id == "xlsx":
        sheets = spec.sheets or (("Sheet", spec.headers, spec.rows),)
        return write_xlsx_input(root / "input.xlsx", sheets)
    if context_id == "json":
        return write_json_input(root / "input.json", spec.json_value)
    return write_text_input(root / "input.txt", spec.text_lines)


def _invoke(spec: InputSpec, path: Path) -> InputObservation:
    """Mirror LegacyInputRunner._invoke, now including the load_inputs orchestration entry."""
    from scoutmb.adapters.files import tabular
    from scoutmb.adapters.files.tabular import TabularAttendeeSource
    from scoutmb.features.ingest.service import IngestService

    entries = {
        "load_csv": lambda: tabular.load_csv(path),
        "load_xlsx": lambda: tabular.load_xlsx(path, spec.sheet_arg),
        "load_json": lambda: tabular.load_json(path),
        "load_text": lambda: tabular.load_text(path),
        "load_inputs": lambda: IngestService(
            sources=(TabularAttendeeSource(sheet_name=spec.sheet_arg),),
            include_adults=spec.include_adults,
        ).load(path),
    }
    try:
        result = entries[spec.entry]()
    except Exception as exc:  # characterizing the real exception contract
        return InputObservation(
            exception_type=type(exc).__name__, message=str(exc).replace(str(path), "<input>")
        )
    return InputObservation(records=tuple((s.name, s.url, s.registrant_type) for s in result))


@pytest.mark.parametrize(("case", "context_id"), execution_params(INPUT_CASES))
def test_package_parsers_match_expectations(case, context_id: str, tmp_path: Path) -> None:
    if context_id not in _FILE_CONTEXTS:
        pytest.skip(f"{context_id} is a legacy-module import probe, not a package context")
    path = _materialize(case.input, context_id, tmp_path)
    assert _invoke(case.input, path) == case.expected_legacy
