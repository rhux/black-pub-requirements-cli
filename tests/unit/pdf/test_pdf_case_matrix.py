"""Package-side PDF-extraction matrix runner (Gate 2 test-coverage close-out).

Drives ``tests/matrix/cases/pdf_cases.py``'s ``PDF_CASES`` against the REAL scoutmb PDF stack
(``scoutmb.adapters.pdf.extract``, ``scoutmb.adapters.pdf.pages``,
``scoutmb.features.ingest.pdf_extract``, ``scoutmb.interfaces.cli.pdf``), dispatching on
``context_id`` exactly as ``pdf_cases.py``'s own module docstring documents. Every synthetic
PDF/image is built through ``tests/factories/pdf_builder.py`` -- never real scout data.

``tests/characterization/test_pdf_matrix.py``, the original runner for this catalog, was deleted
outright in Slice 2b's flat-module retirement (along with ``pdf_to_scouts.py`` itself), leaving
every ``PDF-*`` (case_id, context_id) pair unmarked. This file replaces it using
``tests/matrix/pytest_support.execution_params`` (the idiomatic case-to-parametrize binder --
see ``tests/parity/test_acquisition_parity.py`` for the same pattern elsewhere), rather than
reproducing that retired runner's own bespoke normalized-observation-diffing machinery: each
handler below asserts the specific real-code behavior the case's own rationale/expected fields
document, using the frozen ``PdfCase.expected_legacy`` values as its source of truth.

Three (case_id, context_id) pairs already had a genuinely-covering (if unmarked) test elsewhere
before this file existed, so they are excluded from ``_RUNNER_CASES`` below to avoid a duplicate
matrix_case marker on the same execution key -- the marker was added directly to that existing
test instead:
  * ``PDF-QR-001::extract``   -- tests/packaging/test_core_imports.py
  * ``PDF-SCHEMA-001::schema``-- tests/unit/test_atomic_write.py
  * ``PDF-PAGE-001::extract`` -- tests/unit/pdf/test_pdf_page_001_extra.py (this package; the
    existing candidate in tests/vertical/test_legacy_flows.py already carries a DIFFERENT
    matrix_case marker -- FLOW-SUCCESS-001 -- and pytest_plugins/matrix_gate.py's
    ``item.get_closest_marker("matrix_case")`` only ever reads ONE marker per test item, so
    stacking a second marker on that test would silently lose one of the two).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import cv2
import pytest
from tests.factories.pdf_builder import build_corrupt_pdf, build_multi_qr_image, build_pdf
from tests.matrix.cases.pdf_cases import PDF_CASES, PdfCase, PdfPageSpec
from tests.matrix.pytest_support import execution_params

from scoutmb.adapters.pdf.extract import choose_qr_value, decode_variants
from scoutmb.adapters.pdf.pages import extract_pdf
from scoutmb.features.ingest.pdf_extract import expand_pdf_inputs
from scoutmb.interfaces.cli.pdf import main as pdf_main

_HANDLED_ELSEWHERE = {
    ("PDF-QR-001", "extract"),
    ("PDF-SCHEMA-001", "schema"),
    ("PDF-PAGE-001", "extract"),
}

_RUNNER_CASES: tuple[PdfCase, ...] = tuple(
    case
    for case in PDF_CASES
    if (case.meta.case_id, case.meta.contexts[0]) not in _HANDLED_ELSEWHERE
)

_EXTRACT_LIKE_CONTEXTS = {"extract", "corrupt-open", "corrupt-embedded", "debug"}

_DPIS = (144, 200, 300, 400)


def _xref_normalized(value: str) -> str:
    return re.sub(r"embedded-image:xref-\d+", "embedded-image:xref-<n>", value)


def _substitute(
    argv: tuple[str, ...], pdf_path: Path, out_path: Path, missing_path: Path
) -> list[str]:
    mapping = {"{pdf}": str(pdf_path), "{out}": str(out_path), "{missing}": str(missing_path)}
    return [mapping.get(token, token) for token in argv]


# -------------------------------------------------------------------------------------------
# discover
# -------------------------------------------------------------------------------------------


def _handle_discover(case: PdfCase, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (root / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (root / "b.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (root / "sub").mkdir()
    (root / "sub" / "c.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (root / "notes.txt").write_text("not a pdf", encoding="utf-8")

    recursive = "--recursive" in case.argv
    values = [token for token in case.argv if token != "--recursive"]

    monkeypatch.chdir(root)
    result = expand_pdf_inputs(values, recursive=recursive)
    actual = tuple(path.relative_to(root).as_posix() for path in result)
    assert actual == case.expected_legacy.relative_files


# -------------------------------------------------------------------------------------------
# extract / corrupt-open / corrupt-embedded / debug -- real extract_pdf, attendees + errors
# -------------------------------------------------------------------------------------------


def _handle_extract_like(case: PdfCase, root: Path, context_id: str) -> None:
    pdf_path = root / f"{case.meta.case_id}.pdf"
    if context_id == "corrupt-open":
        build_corrupt_pdf(pdf_path)
    else:
        build_pdf(pdf_path, case.pages)

    debug_dir = root / "debug" if "--debug" in case.argv else None

    if context_id == "corrupt-embedded":
        import fitz

        def _boom_extract_image(self: object, xref: int, *args: object, **kwargs: object) -> None:
            raise ValueError("forced embedded-image extraction failure for PDF-CORRUPT-002")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(fitz.Document, "extract_image", _boom_extract_image)
            attendees, errors = extract_pdf(
                pdf_path, dpis=_DPIS, normalize_case=True, debug_dir=debug_dir
            )
    else:
        attendees, errors = extract_pdf(
            pdf_path, dpis=_DPIS, normalize_case=True, debug_dir=debug_dir
        )

    exp = case.expected_legacy
    assert len(attendees) == len(exp.attendees)
    for actual_a, expected_a in zip(attendees, exp.attendees, strict=True):
        assert actual_a.attendee_name == expected_a.attendee_name
        assert actual_a.name_as_printed == expected_a.name_as_printed
        assert actual_a.registrant_type == expected_a.registrant_type
        assert actual_a.qr_data == expected_a.qr_data
        assert actual_a.source_pdf == expected_a.source_pdf
        assert actual_a.pdf_page == expected_a.pdf_page
        assert _xref_normalized(actual_a.qr_decode_method) == expected_a.qr_decode_method

    assert len(errors) == len(exp.errors)
    for actual_e, expected_e in zip(errors, exp.errors, strict=True):
        assert actual_e.source_pdf == expected_e.source_pdf
        assert actual_e.pdf_page == expected_e.pdf_page
        assert actual_e.attendee_name == expected_e.attendee_name
        assert actual_e.registrant_type == expected_e.registrant_type
        normalized_error = actual_e.error.replace(str(pdf_path), "<pdf>")
        assert normalized_error == expected_e.error

    if context_id == "debug":
        actual_pngs = tuple(
            sorted(p.relative_to(root).as_posix() for p in root.rglob("debug/*.png"))
        )
        assert actual_pngs == exp.relative_files


# -------------------------------------------------------------------------------------------
# choose / decode-multi -- pure helper functions, no PDF built
# -------------------------------------------------------------------------------------------


def _handle_choose(case: PdfCase) -> None:
    values = [page.qr_value for page in case.pages]
    result = choose_qr_value(values)
    assert result == case.expected_legacy.stdout[0]


def _handle_decode_multi(case: PdfCase) -> None:
    values = tuple(page.qr_value for page in case.pages)
    image = build_multi_qr_image(values)
    detector = cv2.QRCodeDetector()
    decoded = decode_variants(image, detector)
    assert tuple(decoded) == case.expected_legacy.stdout


# -------------------------------------------------------------------------------------------
# filter / schema -- run main() and read the generated CSV(s) back
# -------------------------------------------------------------------------------------------


def _handle_filter(case: PdfCase, root: Path) -> None:
    pdf_path = root / f"{case.meta.case_id}.pdf"
    build_pdf(pdf_path, case.pages)
    out_path = root / "out.csv"

    exit_code = pdf_main([str(pdf_path), "-o", str(out_path), *case.argv])
    assert exit_code == 0

    with out_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    exp = case.expected_legacy
    assert len(rows) == len(exp.attendees)
    for row, expected_a in zip(rows, exp.attendees, strict=True):
        assert row["Attendee Name"] == expected_a.attendee_name
        assert row["Name as Printed"] == expected_a.name_as_printed
        assert row["Registrant Type"] == expected_a.registrant_type
        assert row["QR Code Contents"] == expected_a.qr_data
        assert row["Source PDF"] == expected_a.source_pdf
        assert int(row["PDF Page"]) == expected_a.pdf_page
        assert _xref_normalized(row["QR Decode Method"]) == expected_a.qr_decode_method

    assert "out.csv" in exp.relative_files
    assert out_path.exists()


def _handle_schema(case: PdfCase, root: Path) -> None:
    pdf_path = root / f"{case.meta.case_id}.pdf"
    build_pdf(pdf_path, case.pages)
    out_path = root / "out.csv"

    pdf_main([str(pdf_path), "-o", str(out_path), *case.argv])

    if case.meta.member == "error-columns":
        target = out_path.with_name(f"{out_path.stem}.errors.csv")
    else:
        target = out_path
    assert target.exists()

    with target.open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream))
    assert tuple(header) == case.expected_legacy.stdout


# -------------------------------------------------------------------------------------------
# multi-pdf / stale / cli -- run main() and check return code / stdout / files
# -------------------------------------------------------------------------------------------


def _handle_multi_pdf(case: PdfCase, root: Path) -> None:
    exp = case.expected_legacy
    page_a, page_b = case.pages  # page_a -> "b.pdf", page_b -> "a.pdf" (see module docstring)
    a_pdf = build_pdf(root / "a.pdf", (page_b,))
    b_pdf = build_pdf(root / "b.pdf", (page_a,))
    out_path = root / "out.csv"

    # Positional args deliberately NOT in alphabetical order, to prove main() follows
    # expand_pdf_inputs' sorted discovery order rather than argv order.
    exit_code = pdf_main([str(b_pdf), str(a_pdf), "-o", str(out_path)])
    assert exit_code == 0

    with out_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(exp.attendees)
    for row, expected_a in zip(rows, exp.attendees, strict=True):
        assert row["Attendee Name"] == expected_a.attendee_name
        assert row["Source PDF"] == expected_a.source_pdf
        assert row["QR Code Contents"] == expected_a.qr_data
        assert _xref_normalized(row["QR Decode Method"]) == expected_a.qr_decode_method

    for rel in exp.relative_files:
        assert (root / rel).exists()


def _handle_stale(case: PdfCase, root: Path) -> None:
    out_path = root / "out.csv"
    errors_path = root / "out.errors.csv"

    stale_pdf = build_pdf(
        root / "stale-source.pdf", (PdfPageSpec("Stale Person", "Youth", "", "none"),)
    )
    first_exit = pdf_main([str(stale_pdf), "-o", str(out_path), "--render-dpi", "72"])
    assert first_exit == 0
    assert errors_path.exists()  # precondition: a stale error csv is left behind

    pdf_path = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
    second_exit = pdf_main([str(pdf_path), "-o", str(out_path)])

    assert second_exit == case.expected_legacy.return_code
    assert not errors_path.exists()  # main()'s stale-removal branch ran
    for rel in case.expected_legacy.relative_files:
        assert (root / rel).exists()


def _handle_cli(case: PdfCase, root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exp = case.expected_legacy
    member = case.meta.member
    pdf_path = root / f"{case.meta.case_id}.pdf"
    if case.pages:
        build_pdf(pdf_path, case.pages)
    out_path = root / "out.csv"
    missing_path = root / "does-not-exist.pdf"
    argv = _substitute(case.argv, pdf_path, out_path, missing_path)

    if member == "help":
        with pytest.raises(SystemExit) as exc_info:
            pdf_main(argv)
        assert exc_info.value.code == exp.return_code
        captured = capsys.readouterr()
        assert captured.out.strip().lower().startswith("usage")
        return

    exit_code = pdf_main(argv)
    captured = capsys.readouterr()
    assert exit_code == exp.return_code

    if member == "no-match":
        assert exp.stderr[0] in captured.err
        return
    if member in ("dpi-low", "dpi-high"):
        assert exp.stderr[0] in captured.err
        return

    # success / strict-exit / quiet: normalize the tmp root to "<root>" and compare exact lines.
    stdout_lines = tuple(
        line.replace(str(root), "<root>") for line in captured.out.strip("\n").splitlines()
    )
    assert stdout_lines == exp.stdout
    for rel in exp.relative_files:
        assert (root / rel).exists()


# -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("case", "context_id"), execution_params(_RUNNER_CASES))
def test_pdf_case(
    case: PdfCase,
    context_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path.resolve()

    if context_id == "discover":
        _handle_discover(case, root, monkeypatch)
    elif context_id in _EXTRACT_LIKE_CONTEXTS:
        _handle_extract_like(case, root, context_id)
    elif context_id == "choose":
        _handle_choose(case)
    elif context_id == "decode-multi":
        _handle_decode_multi(case)
    elif context_id == "filter":
        _handle_filter(case, root)
    elif context_id == "schema":
        _handle_schema(case, root)
    elif context_id == "multi-pdf":
        _handle_multi_pdf(case, root)
    elif context_id == "stale":
        _handle_stale(case, root)
    elif context_id == "cli":
        _handle_cli(case, root, capsys)
    else:
        pytest.fail(f"no PDF matrix runner handler for context {context_id!r}")
