"""Typed matrix execution of the legacy PDF-extraction characterization catalog (Task 18).

Each ``PDF-*`` case declares one execution context; ``execution_params`` expands them. The
runner builds a real synthetic PDF (or fixture tree) below pytest's ``tmp_path`` via the
deterministic builders in ``tests/factories/pdf_builder`` and calls the REAL ``pdf_to_scouts``
functions -- ``expand_pdf_inputs`` / ``extract_pdf`` / ``choose_qr_value`` / ``decode_variants``
/ ``main``. Nothing here mocks the extraction logic except ``PDF-CORRUPT-002``, which patches
only ``cv2.imdecode`` (the single embedded-image decode call) to force the render fallback.

No test writes outside ``tmp_path`` and no PDF or PNG binary fixture is committed: every byte is
generated in-process per test.
"""

from __future__ import annotations

import io
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import pytest
from tests.factories.pdf_builder import (
    build_corrupt_pdf,
    build_multi_qr_image,
    build_pdf,
)
from tests.matrix.cases.pdf_cases import (
    PDF_CASES,
    ExtractedAttendeeObservation,
    ExtractionErrorObservation,
    PdfCase,
    PdfObservation,
    PdfPageSpec,
)
from tests.matrix.pytest_support import execution_params

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_XREF = re.compile(r"embedded-image:xref-\d+")


def _norm_method(method: str) -> str:
    return _XREF.sub("embedded-image:xref-<n>", method)


def _rel_files(root: Path, ignore: set[Path]) -> tuple[str, ...]:
    resolved_ignore = {path.resolve() for path in ignore}
    names = [
        os.path.relpath(path, root).replace(os.sep, "/")
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.resolve() not in resolved_ignore
    ]
    return tuple(sorted(names, key=str.lower))


class LegacyPdfRunner:
    """Runner[PdfCase, PdfObservation] over the real pdf_to_scouts extraction and CLI."""

    def __init__(self, context_id: str) -> None:
        self.context_id = context_id

    def run(self, case: PdfCase, *, root: Path) -> PdfObservation:
        handler = getattr(self, f"_ctx_{self.context_id.replace('-', '_')}")
        return handler(case, root)

    # -- extraction contexts ---------------------------------------------------------------

    def _extract_dpis(self, case: PdfCase) -> tuple[int, ...]:
        # A vector QR must decode through the render fallback at 144 DPI; every other extract
        # case either decodes from the embedded image (DPI-independent) or fails fast, so a
        # single low DPI keeps the expensive render-failure path quick.
        if any(page.qr_mode == "vector" for page in case.pages):
            return (144,)
        return (72,)

    def _observe_extraction(
        self, attendees: list, errors: list, root: Path, extra_files: tuple[str, ...] = ()
    ) -> PdfObservation:
        att = tuple(
            ExtractedAttendeeObservation(
                a.attendee_name,
                a.name_as_printed,
                a.registrant_type,
                a.qr_data,
                a.source_pdf,
                a.pdf_page,
                _norm_method(a.qr_decode_method),
            )
            for a in attendees
        )
        errs = tuple(
            ExtractionErrorObservation(
                e.source_pdf, e.pdf_page, e.attendee_name, e.registrant_type, e.error
            )
            for e in errors
        )
        return PdfObservation(attendees=att, errors=errs, relative_files=extra_files)

    def _ctx_extract(self, case: PdfCase, root: Path) -> PdfObservation:
        import pdf_to_scouts as legacy

        pdf = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
        attendees, errors = legacy.extract_pdf(pdf, self._extract_dpis(case), True, None)
        return self._observe_extraction(attendees, errors, root)

    def _ctx_corrupt_embedded(self, case: PdfCase, root: Path) -> PdfObservation:
        import pdf_to_scouts as legacy

        pdf = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
        boom = legacy.cv2.error("synthetic embedded-image decode failure")
        with mock.patch.object(legacy.cv2, "imdecode", side_effect=boom):
            attendees, errors = legacy.extract_pdf(pdf, (144,), True, None)
        return self._observe_extraction(attendees, errors, root)

    def _ctx_corrupt_open(self, case: PdfCase, root: Path) -> PdfObservation:
        # A non-parseable PDF fails at the fitz.open() guard before any page or attendee
        # loop runs, so the observation is error-only; the raised message embeds the absolute
        # fixture path, which is normalized to "<pdf>" for a deterministic assertion.
        import pdf_to_scouts as legacy

        pdf = build_corrupt_pdf(root / f"{case.meta.case_id}.pdf")
        attendees, errors = legacy.extract_pdf(pdf, (72,), True, None)
        observed = self._observe_extraction(attendees, errors, root)
        errs = tuple(
            ExtractionErrorObservation(
                e.source_pdf,
                e.pdf_page,
                e.attendee_name,
                e.registrant_type,
                e.error.replace(str(pdf), "<pdf>"),
            )
            for e in observed.errors
        )
        return PdfObservation(attendees=observed.attendees, errors=errs)

    def _ctx_debug(self, case: PdfCase, root: Path) -> PdfObservation:
        import pdf_to_scouts as legacy

        pdf = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
        debug_dir = root / "debug" if "--debug" in case.argv else None
        attendees, errors = legacy.extract_pdf(pdf, (72,), True, debug_dir)
        return self._observe_extraction(attendees, errors, root, _rel_files(root, {pdf}))

    # -- helper-seam contexts --------------------------------------------------------------

    def _ctx_choose(self, case: PdfCase, root: Path) -> PdfObservation:
        import pdf_to_scouts as legacy

        chosen = legacy.choose_qr_value([page.qr_value for page in case.pages])
        return PdfObservation(stdout=(chosen,))

    def _ctx_decode_multi(self, case: PdfCase, root: Path) -> PdfObservation:
        import pdf_to_scouts as legacy

        image = build_multi_qr_image(tuple(page.qr_value for page in case.pages))
        decoded = legacy.decode_variants(image, legacy.cv2.QRCodeDetector())
        return PdfObservation(stdout=tuple(decoded))

    # -- discovery context -----------------------------------------------------------------

    def _ctx_discover(self, case: PdfCase, root: Path) -> PdfObservation:
        import pdf_to_scouts as legacy

        for name in ("a.pdf", "b.pdf"):
            build_pdf(root / name, (PdfPageSpec("Avery Example", "Youth", "u", "none"),))
        (root / "sub").mkdir()
        build_pdf(root / "sub" / "c.pdf", (PdfPageSpec("Avery Example", "Youth", "u", "none"),))
        (root / "notes.txt").write_text("not a pdf", encoding="utf-8")

        recursive = "--recursive" in case.argv
        tokens = [tok for tok in case.argv if tok != "--recursive"]
        inputs = [str(root) if tok == "." else str(root / tok) for tok in tokens]
        discovered = legacy.expand_pdf_inputs(inputs, recursive)
        root_resolved = root.resolve()
        names = tuple(
            os.path.relpath(path, root_resolved).replace(os.sep, "/") for path in discovered
        )
        return PdfObservation(relative_files=names)

    # -- CLI / CSV contexts ----------------------------------------------------------------

    def _run_main(self, argv: list[str]) -> tuple[int, list[str], list[str]]:
        import pdf_to_scouts as legacy

        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = legacy.main(argv)
        except SystemExit as exc:  # argparse --help / usage errors
            code = int(exc.code or 0)
        return code, out.getvalue().splitlines(), err.getvalue().splitlines()

    def _norm_lines(self, lines: list[str], root: Path) -> tuple[str, ...]:
        token = str(root)
        return tuple(line.replace(token, "<root>") for line in lines)

    def _parse_attendee_csv(self, path: Path, source_map: dict[str, str]) -> tuple:
        import csv

        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        parsed = []
        for row in rows:
            source = source_map.get(row["Source PDF"], row["Source PDF"])
            parsed.append(
                ExtractedAttendeeObservation(
                    row["Attendee Name"],
                    row["Name as Printed"],
                    row["Registrant Type"],
                    row["QR Code Contents"],
                    source,
                    int(row["PDF Page"]),
                    _norm_method(row["QR Decode Method"]),
                )
            )
        return tuple(parsed)

    def _ctx_filter(self, case: PdfCase, root: Path) -> PdfObservation:
        pdf = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
        out = root / "out.csv"
        code, _, _ = self._run_main([str(pdf), "-o", str(out), *case.argv])
        assert code == 0, f"filter run exited {code}"
        attendees = self._parse_attendee_csv(out, {pdf.name: pdf.name})
        return PdfObservation(attendees=attendees, relative_files=_rel_files(root, {pdf}))

    def _ctx_schema(self, case: PdfCase, root: Path) -> PdfObservation:
        import csv

        pdf = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
        out = root / "out.csv"
        self._run_main([str(pdf), "-o", str(out), *case.argv])
        # The case's declared axis member says explicitly which CSV its expected header belongs
        # to ("error-columns" vs "attendee-columns") -- key off that stated intent rather than an
        # argv flag ("--render-dpi") that only happens to correlate with a failing extraction
        # today. A future case combining --render-dpi with a successful extraction would still
        # read the right file.
        target = out.with_name("out.errors.csv") if case.meta.member == "error-columns" else out
        with target.open("r", encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream))
        return PdfObservation(stdout=tuple(header))

    def _ctx_multi_pdf(self, case: PdfCase, root: Path) -> PdfObservation:
        # pages[0] -> b.pdf, pages[1] -> a.pdf so the sorted-path processing order (a before b)
        # is the reverse of both the argument order and the page order.
        pdf_b = build_pdf(root / "b.pdf", (case.pages[0],))
        pdf_a = build_pdf(root / "a.pdf", (case.pages[1],))
        out = root / "out.csv"
        code, _, _ = self._run_main([str(pdf_b), str(pdf_a), "-o", str(out)])
        assert code == 0
        attendees = self._parse_attendee_csv(out, {"a.pdf": "a.pdf", "b.pdf": "b.pdf"})
        return PdfObservation(attendees=attendees, relative_files=_rel_files(root, set()))

    def _ctx_cli(self, case: PdfCase, root: Path) -> PdfObservation:
        inputs: set[Path] = set()
        out = root / "out.csv"
        argv: list[str] = []
        for token in case.argv:
            if token == "{pdf}":
                pdf = build_pdf(root / f"{case.meta.case_id}.pdf", case.pages)
                inputs.add(pdf)
                argv.append(str(pdf))
            elif token == "{out}":
                argv.append(str(out))
            elif token == "{missing}":
                argv.append(str(root / "nope.pdf"))
            else:
                argv.append(token)

        code, stdout, stderr = self._run_main(argv)
        if "--help" in case.argv:
            stdout = ["usage"] if stdout and stdout[0].startswith("usage") else stdout
        return PdfObservation(
            return_code=code,
            stdout=self._norm_lines(stdout, root),
            stderr=self._norm_lines(stderr, root),
            relative_files=_rel_files(root, inputs),
        )

    def _ctx_stale(self, case: PdfCase, root: Path) -> PdfObservation:
        warn = build_pdf(
            root / f"{case.meta.case_id}-warn.pdf",
            (PdfPageSpec("Avery Example", "Youth", "https://x/y", "none"),),
        )
        good = build_pdf(root / f"{case.meta.case_id}-good.pdf", case.pages)
        out = root / "out.csv"
        # First run leaves out.errors.csv behind; the second clean run must remove it.
        self._run_main([str(warn), "-o", str(out), "--render-dpi", "72"])
        code, _, _ = self._run_main([str(good), "-o", str(out)])
        return PdfObservation(
            return_code=code, relative_files=_rel_files(root, {warn, good})
        )


def _observe(case: PdfCase, context_id: str, root: Path) -> PdfObservation:
    return LegacyPdfRunner(context_id).run(case, root=root)


@pytest.mark.parametrize(("case", "context_id"), execution_params(PDF_CASES))
def test_pdf_case(case: PdfCase, context_id: str, tmp_path: Path) -> None:
    observed = _observe(case, context_id, tmp_path)
    assert observed == case.expected_legacy


def test_pdf_registry_is_structurally_valid() -> None:
    # Validate the PDF catalog in isolation. ALL_CASES is intentionally not wired into the
    # lane-accounting registry until Task 22, so we assemble the PDF-domain slice directly.
    from tests.matrix.axes import AXES
    from tests.matrix.boundaries import BOUNDARIES
    from tests.matrix.model import Domain
    from tests.matrix.registry import validate_registry

    pdf_metas = [case.meta for case in PDF_CASES]
    pdf_axes = [axis for axis in AXES if axis.domain is Domain.PDF]
    pdf_boundaries = [b for b in BOUNDARIES if b.domain is Domain.PDF]

    errors = validate_registry(pdf_metas, pdf_axes, pdf_boundaries, [], [])
    assert errors == ()
