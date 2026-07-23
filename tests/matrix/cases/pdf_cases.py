"""PDF-extraction characterization catalog (Task 18).

Every row here is ``preserve`` classification: it pins the *current* behavior of
``pdf_to_scouts`` (``expand_pdf_inputs`` / ``extract_page_identity`` / ``normalize_obvious_case``
/ ``decode_embedded_qr`` / ``decode_rendered_qr`` / ``extract_pdf`` / ``write_attendees_csv`` /
``write_errors_csv`` / ``main``), not a desired future behavior. This module holds only frozen
data -- it never imports the legacy application (``pdf_to_scouts``) or any optional third-party
package (``fitz`` / ``cv2`` / ``numpy``). The runner and builder in
``tests/characterization/test_pdf_matrix.py`` and ``tests/factories/pdf_builder.py`` perform
the real imports and PDF generation.

Observation encoding by execution context (each case declares exactly one context):

* ``extract`` / ``corrupt-embedded`` / ``debug`` -- ``attendees`` + ``errors`` from the real
  ``extract_pdf`` (``debug`` additionally records the written PNG in ``relative_files``).
* ``discover`` -- ``relative_files`` are the POSIX paths ``expand_pdf_inputs`` discovered,
  relative to the fixture root.
* ``choose`` -- ``stdout`` holds the single value ``choose_qr_value`` returns.
* ``decode-multi`` -- ``stdout`` holds the deduplicated values ``decode_variants`` returns for a
  stitched multi-symbol image (raw multi-symbol *order* is an OpenCV property that varies across
  builds, so these cases pin identical symbols collapsing to one value rather than raw order).
* ``filter`` / ``schema`` -- run ``main`` and read the generated CSV back: ``filter`` reports the
  parsed attendee rows + output ``relative_files``; ``schema`` reports the exact CSV header
  columns in ``stdout``.
* ``cli`` / ``multi-pdf`` / ``stale`` -- run ``main`` and capture ``return_code`` plus normalized
  ``stdout`` / ``stderr`` line tuples and output ``relative_files``.

Non-deterministic fragments are normalized by the runner before comparison: an embedded xref
number becomes ``embedded-image:xref-<n>``, the fixture root becomes ``<root>``, and a failed
PDF's absolute path inside an error message becomes ``<pdf>``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tests.matrix.model import (
    CaseMetadata,
    Classification,
    Domain,
    EvidenceKind,
)

# Synthetic identities only -- never real scout data.
NAME_A = "Avery Example"
NAME_B = "Bailey Example"
URL_A = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_A"
URL_B = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_B"
OTHER_URL = "https://example.com/other-token-XYZ"

_EMBEDDED = "embedded-image:xref-<n>"
_RENDERED = "rendered:144dpi:full-page"


@dataclass(frozen=True, slots=True)
class PdfPageSpec:
    name: str
    registrant_type: str
    qr_value: str
    qr_mode: Literal["embedded", "vector", "none"]


@dataclass(frozen=True, slots=True)
class ExtractedAttendeeObservation:
    attendee_name: str
    name_as_printed: str
    registrant_type: str
    qr_data: str
    source_pdf: str
    pdf_page: int
    qr_decode_method: str


@dataclass(frozen=True, slots=True)
class ExtractionErrorObservation:
    source_pdf: str
    pdf_page: int
    attendee_name: str
    registrant_type: str
    error: str


@dataclass(frozen=True, slots=True)
class PdfObservation:
    attendees: tuple[ExtractedAttendeeObservation, ...] = ()
    errors: tuple[ExtractionErrorObservation, ...] = ()
    return_code: int = 0
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    relative_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PdfCase:
    meta: CaseMetadata
    pages: tuple[PdfPageSpec, ...]
    argv: tuple[str, ...]
    expected_legacy: PdfObservation


def _meta(
    case_id: str,
    axis_id: str,
    member: str,
    context: str,
    rationale: str,
    evidence_reference: str,
) -> CaseMetadata:
    return CaseMetadata(
        case_id=case_id,
        axis_id=axis_id,
        member=member,
        domain=Domain.PDF,
        classification=Classification.PRESERVE,
        evidence=EvidenceKind.CURRENT_BRANCH,
        rationale=rationale,
        contexts=(context,),
        evidence_reference=evidence_reference,
    )


def _embedded(name: str, registrant_type: str, value: str = URL_A) -> PdfPageSpec:
    return PdfPageSpec(name, registrant_type, value, "embedded")


# --------------------------------------------------------------------------------------------
# PDF-DISC: expand_pdf_inputs discovery over files, directories, globs, recursion, overlap.
# The ``discover`` runner builds a fixed tree (a.pdf, b.pdf, sub/c.pdf, notes.txt) below root
# and the argv selects how it is discovered. Members map to pdf_to_scouts.expand_pdf_inputs.
# --------------------------------------------------------------------------------------------
_DISC_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-DISC-001",
            "PDF-DISC",
            "file",
            "discover",
            "A direct .pdf file argument resolves to exactly that one file.",
            "pdf_to_scouts.expand_pdf_inputs lines 145-148",
        ),
        (),
        ("a.pdf",),
        PdfObservation(relative_files=("a.pdf",)),
    ),
    PdfCase(
        _meta(
            "PDF-DISC-002",
            "PDF-DISC",
            "directory",
            "discover",
            "A directory argument discovers its top-level *.pdf files but not subdirectories.",
            "pdf_to_scouts.expand_pdf_inputs lines 150-153",
        ),
        (),
        (".",),
        PdfObservation(relative_files=("a.pdf", "b.pdf")),
    ),
    PdfCase(
        _meta(
            "PDF-DISC-003",
            "PDF-DISC",
            "glob",
            "discover",
            "A glob pattern is expanded in-process and keeps only .pdf matches.",
            "pdf_to_scouts.expand_pdf_inputs lines 155-160",
        ),
        (),
        ("*.pdf",),
        PdfObservation(relative_files=("a.pdf", "b.pdf")),
    ),
    PdfCase(
        _meta(
            "PDF-DISC-004",
            "PDF-DISC",
            "recursive",
            "discover",
            "A recursive directory search also finds *.pdf files in subdirectories.",
            "pdf_to_scouts.expand_pdf_inputs line 151 rglob branch",
        ),
        (),
        ("--recursive", "."),
        PdfObservation(relative_files=("a.pdf", "b.pdf", "sub/c.pdf")),
    ),
    PdfCase(
        _meta(
            "PDF-DISC-005",
            "PDF-DISC",
            "overlapping",
            "discover",
            "Overlapping file and directory inputs are deduplicated to one sorted path list.",
            "pdf_to_scouts.expand_pdf_inputs lines 165-171 dedup",
        ),
        (),
        ("a.pdf", "."),
        PdfObservation(relative_files=("a.pdf", "b.pdf")),
    ),
    PdfCase(
        _meta(
            "PDF-DISC-006",
            "PDF-DISC",
            "missing",
            "discover",
            "A missing path and a non-PDF file both contribute nothing to discovery.",
            "pdf_to_scouts.expand_pdf_inputs lines 145-164 skip non-pdf/missing",
        ),
        (),
        ("missing.pdf", "notes.txt"),
        PdfObservation(relative_files=()),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-ID: extract_page_identity + extract_pdf field presence. The builder emits each identity
# label only when its value is present, so an absent field is genuinely absent. A page is
# emitted as an attendee when any of name/type/QR is present; each absent field adds one
# "Missing ..." error. Members map to pdf_to_scouts.extract_page_identity / extract_pdf.
# --------------------------------------------------------------------------------------------
_ID_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-ID-001",
            "PDF-ID",
            "all-fields",
            "extract",
            "A page with name, registrant type, and an embedded QR yields one clean attendee.",
            "pdf_to_scouts.extract_pdf lines 400-445",
        ),
        (_embedded(NAME_A, "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-ID-001.pdf", 1, _EMBEDDED
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-002",
            "PDF-ID",
            "missing-name",
            "extract",
            "A page missing the attendee name still emits the attendee and one name error.",
            "pdf_to_scouts.extract_pdf lines 409-425",
        ),
        (_embedded("", "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "", "", "Youth", URL_A, "PDF-ID-002.pdf", 1, _EMBEDDED
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-002.pdf", 1, "", "Youth", "Missing attendee name"
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-003",
            "PDF-ID",
            "missing-type",
            "extract",
            "A page missing the registrant type emits the attendee and one type error.",
            "pdf_to_scouts.extract_pdf lines 412-425",
        ),
        (_embedded(NAME_A, ""),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "", URL_A, "PDF-ID-003.pdf", 1, _EMBEDDED
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-003.pdf", 1, NAME_A, "", "Missing registrant type"
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-004",
            "PDF-ID",
            "missing-qr",
            "extract",
            "A page with no decodable QR emits the attendee and one QR error.",
            "pdf_to_scouts.extract_pdf lines 414-425",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "none"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", "", "PDF-ID-004.pdf", 1, ""
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-004.pdf", 1, NAME_A, "Youth", "Missing QR code"
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-005",
            "PDF-ID",
            "missing-name-type",
            "extract",
            "A page with only a QR emits the attendee and one combined name+type error.",
            "pdf_to_scouts.extract_pdf lines 409-425 join",
        ),
        (_embedded("", ""),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "", "", "", URL_A, "PDF-ID-005.pdf", 1, _EMBEDDED
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-005.pdf", 1, "", "", "Missing attendee name, registrant type"
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-006",
            "PDF-ID",
            "name-qr",
            "extract",
            "A page carrying name and QR but no type is the type-missing path, framed by "
            "what is present.",
            "pdf_to_scouts.extract_pdf lines 412-425",
        ),
        (_embedded(NAME_B, "", URL_B),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_B, NAME_B, "", URL_B, "PDF-ID-006.pdf", 1, _EMBEDDED
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-006.pdf", 1, NAME_B, "", "Missing registrant type"
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-007",
            "PDF-ID",
            "type-qr",
            "extract",
            "A page carrying type and QR but no name is the name-missing path, framed by "
            "what is present.",
            "pdf_to_scouts.extract_pdf lines 409-425",
        ),
        (_embedded("", "Adult", URL_B),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "", "", "Adult", URL_B, "PDF-ID-007.pdf", 1, _EMBEDDED
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-007.pdf", 1, "", "Adult", "Missing attendee name"
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-ID-008",
            "PDF-ID",
            "all-missing",
            "extract",
            "A page with nothing present emits no attendee and one three-part missing error.",
            "pdf_to_scouts.extract_pdf lines 409-434 append guard",
        ),
        (PdfPageSpec("", "", URL_A, "none"),),
        (),
        PdfObservation(
            errors=(
                ExtractionErrorObservation(
                    "PDF-ID-008.pdf",
                    1,
                    "",
                    "",
                    "Missing attendee name, registrant type, QR code",
                ),
            ),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-CASE: normalize_obvious_case. ``extract`` cases observe the default-on normalization;
# the disabled case runs main with --no-normalize-obvious-case and reads the CSV back so the
# preserved capitalization is visible. Members map to pdf_to_scouts.normalize_obvious_case.
# --------------------------------------------------------------------------------------------
_CASE_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-CASE-001",
            "PDF-CASE",
            "normalize-miles",
            "extract",
            "The two-leading-caps artifact 'MIles' is normalized to 'Miles' while the printed "
            "form is retained.",
            "pdf_to_scouts.normalize_obvious_case lines 203-209",
        ),
        (_embedded("MIles Smith", "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "Miles Smith", "MIles Smith", "Youth", URL_A, "PDF-CASE-001.pdf", 1, _EMBEDDED
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CASE-002",
            "PDF-CASE",
            "normalization-disabled",
            "filter",
            "With --no-normalize-obvious-case the 'MIles' capitalization survives into the CSV.",
            "pdf_to_scouts.main line 543 passes normalize_case",
        ),
        (_embedded("MIles Smith", "Youth"),),
        ("--no-normalize-obvious-case",),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "MIles Smith",
                    "MIles Smith",
                    "Youth",
                    URL_A,
                    "PDF-CASE-002.pdf",
                    1,
                    _EMBEDDED,
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CASE-003",
            "PDF-CASE",
            "preserve-mcdonald",
            "extract",
            "A valid internal-caps surname 'McDonald' is left unchanged by normalization.",
            "pdf_to_scouts.normalize_obvious_case docstring lines 198-201",
        ),
        (_embedded("Ronald McDonald", "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "Ronald McDonald",
                    "Ronald McDonald",
                    "Youth",
                    URL_A,
                    "PDF-CASE-003.pdf",
                    1,
                    _EMBEDDED,
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CASE-004",
            "PDF-CASE",
            "preserve-aj",
            "extract",
            "A two-letter all-caps initialism 'AJ' is left unchanged by normalization.",
            "pdf_to_scouts.normalize_obvious_case line 205 length guard",
        ),
        (_embedded("AJ Jones", "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    "AJ Jones", "AJ Jones", "Youth", URL_A, "PDF-CASE-004.pdf", 1, _EMBEDDED
                ),
            ),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-QR: the two decode tiers and the value-selection helper. Members map to
# pdf_to_scouts.decode_embedded_qr / decode_rendered_qr / choose_qr_value / decode_variants.
# --------------------------------------------------------------------------------------------
_QR_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-QR-001",
            "PDF-QR",
            "embedded",
            "extract",
            "An embedded raster QR decodes through the fast embedded-image tier.",
            "pdf_to_scouts.decode_embedded_qr lines 324-335",
        ),
        (_embedded(NAME_A, "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-QR-001.pdf", 1, _EMBEDDED
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-QR-002",
            "PDF-QR",
            "rendered",
            "extract",
            "A vector-drawn QR with no embedded image decodes through the rendered-page "
            "fallback at the first DPI.",
            "pdf_to_scouts.decode_rendered_qr lines 373-380",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "vector"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-QR-002.pdf", 1, _RENDERED
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-QR-003",
            "PDF-QR",
            "preferred",
            "choose",
            "When both a ScoutingEvent value and another value are decoded, the ScoutingEvent "
            "value wins regardless of position.",
            "pdf_to_scouts.choose_qr_value lines 292-295",
        ),
        (
            PdfPageSpec("", "", OTHER_URL, "embedded"),
            PdfPageSpec("", "", URL_A, "embedded"),
        ),
        (),
        PdfObservation(stdout=(URL_A,)),
    ),
    PdfCase(
        _meta(
            "PDF-QR-004",
            "PDF-QR",
            "first-other",
            "choose",
            "With no ScoutingEvent value present, the first decoded value is chosen.",
            "pdf_to_scouts.choose_qr_value line 295 fallback",
        ),
        (
            PdfPageSpec("", "", "alpha-token", "embedded"),
            PdfPageSpec("", "", "beta-token", "embedded"),
        ),
        (),
        PdfObservation(stdout=("alpha-token",)),
    ),
    PdfCase(
        _meta(
            "PDF-QR-005",
            "PDF-QR",
            "multi-symbol",
            "decode-multi",
            "Two identical QR symbols in one image collapse to a single deduplicated value.",
            "pdf_to_scouts.decode_variants lines 245-278 seen-set dedup",
        ),
        (
            PdfPageSpec("", "", URL_A, "embedded"),
            PdfPageSpec("", "", URL_A, "embedded"),
        ),
        (),
        PdfObservation(stdout=(URL_A,)),
    ),
    PdfCase(
        _meta(
            "PDF-QR-006",
            "PDF-QR",
            "total-failure",
            "extract",
            "A page with no QR at all fails both tiers and produces an empty decode method.",
            "pdf_to_scouts.extract_pdf lines 404-407 both tiers empty",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "none"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", "", "PDF-QR-006.pdf", 1, ""
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-QR-006.pdf", 1, NAME_A, "Youth", "Missing QR code"
                ),
            ),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-PAGE: attendee ordering within and across PDFs. Members map to pdf_to_scouts.extract_pdf
# page enumeration and main's file-loop over expand_pdf_inputs' sorted output.
# --------------------------------------------------------------------------------------------
_PAGE_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-PAGE-001",
            "PDF-PAGE",
            "multipage-order",
            "extract",
            "Attendees from a multi-page PDF are emitted in ascending page order.",
            "pdf_to_scouts.extract_pdf line 400 enumerate start=1",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Youth", URL_B),
        ),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-PAGE-001.pdf", 1, _EMBEDDED
                ),
                ExtractedAttendeeObservation(
                    NAME_B, NAME_B, "Youth", URL_B, "PDF-PAGE-001.pdf", 2, _EMBEDDED
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-PAGE-002",
            "PDF-PAGE",
            "multi-pdf-order",
            "multi-pdf",
            "Across multiple PDFs, output rows follow expand_pdf_inputs' case-insensitive path "
            "sort, not the argument order.",
            "pdf_to_scouts.expand_pdf_inputs line 167 sort key + main loop line 535",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Youth", URL_B),
        ),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_B, NAME_B, "Youth", URL_B, "a.pdf", 1, _EMBEDDED
                ),
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "b.pdf", 1, _EMBEDDED
                ),
            ),
            relative_files=("a.pdf", "b.pdf", "out.csv"),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-CORRUPT: malformed-PDF open path and a corrupt embedded image ignored in favor of the
# render fallback. Members map to pdf_to_scouts.extract_pdf's open guard and decode fallback.
# --------------------------------------------------------------------------------------------
_CORRUPT_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-CORRUPT-001",
            "PDF-CORRUPT",
            "corrupt-open",
            "extract",
            "A file that is not a parseable PDF yields exactly one bounded page-0 open error.",
            "pdf_to_scouts.extract_pdf lines 394-397 open guard",
        ),
        (),
        (),
        PdfObservation(
            errors=(
                ExtractionErrorObservation(
                    "PDF-CORRUPT-001.pdf",
                    0,
                    "",
                    "",
                    "Could not open PDF: Failed to open file '<pdf>' as type pdf.",
                ),
            ),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CORRUPT-002",
            "PDF-CORRUPT",
            "corrupt-embedded",
            "corrupt-embedded",
            "When the embedded-image decode raises, the page still decodes through the rendered "
            "fallback.",
            "pdf_to_scouts.decode_embedded_qr lines 329-330 except then extract_pdf fallback 407",
        ),
        (_embedded(NAME_A, "Youth"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-CORRUPT-002.pdf", 1, _RENDERED
                ),
            ),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-DEBUG: the --debug-dir render-dump on decode failure. Members map to pdf_to_scouts.
# extract_pdf lines 427-432 (debug branch present vs absent).
# --------------------------------------------------------------------------------------------
_DEBUG_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-DEBUG-001",
            "PDF-DEBUG",
            "with-root",
            "debug",
            "A QR-decode failure with a debug root writes one page render PNG for inspection.",
            "pdf_to_scouts.extract_pdf lines 427-432 debug write",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "none"),),
        ("--debug",),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", "", "PDF-DEBUG-001.pdf", 1, ""
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-DEBUG-001.pdf", 1, NAME_A, "Youth", "Missing QR code"
                ),
            ),
            relative_files=("debug/PDF-DEBUG-001-page-001.png",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-DEBUG-002",
            "PDF-DEBUG",
            "without-root",
            "debug",
            "The same QR-decode failure without a debug root writes no render PNG.",
            "pdf_to_scouts.extract_pdf line 427 debug_dir is None guard",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "none"),),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", "", "PDF-DEBUG-002.pdf", 1, ""
                ),
            ),
            errors=(
                ExtractionErrorObservation(
                    "PDF-DEBUG-002.pdf", 1, NAME_A, "Youth", "Missing QR code"
                ),
            ),
            relative_files=(),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-FILTER: main's retain loop -- adult exclusion, custom adult types, include-adults,
# scoutingevent-only, and duplicate handling. Members map to pdf_to_scouts.main lines 555-567.
# --------------------------------------------------------------------------------------------
_FILTER_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-FILTER-001",
            "PDF-FILTER",
            "default-adult",
            "filter",
            "An Adult registrant is excluded by default, leaving only the youth row.",
            "pdf_to_scouts.main line 556 adult filter",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Adult", URL_B),
        ),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-FILTER-001.pdf", 1, _EMBEDDED
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-FILTER-002",
            "PDF-FILTER",
            "custom-adult",
            "filter",
            "A --adult-type value extends the exclusion set case-insensitively.",
            "pdf_to_scouts.main line 531 adult_types union",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Volunteer", URL_B),
        ),
        ("--adult-type", "Volunteer"),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-FILTER-002.pdf", 1, _EMBEDDED
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-FILTER-003",
            "PDF-FILTER",
            "include-adults",
            "filter",
            "With --include-adults, adult rows are retained alongside youth rows.",
            "pdf_to_scouts.main line 556 include_adults guard",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Adult", URL_B),
        ),
        ("--include-adults",),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-FILTER-003.pdf", 1, _EMBEDDED
                ),
                ExtractedAttendeeObservation(
                    NAME_B, NAME_B, "Adult", URL_B, "PDF-FILTER-003.pdf", 2, _EMBEDDED
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-FILTER-004",
            "PDF-FILTER",
            "scoutingevent-only",
            "filter",
            "With --scoutingevent-only, a row whose QR is not a ScoutingEvent URL is dropped.",
            "pdf_to_scouts.main line 559 scoutingevent_only guard",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Youth", OTHER_URL),
        ),
        ("--scoutingevent-only",),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-FILTER-004.pdf", 1, _EMBEDDED
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-FILTER-005",
            "PDF-FILTER",
            "duplicate-removed",
            "filter",
            "By default a repeated QR value is retained only for its first-seen row.",
            "pdf_to_scouts.main lines 562-566 dedup",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Youth", URL_A),
        ),
        (),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-FILTER-005.pdf", 1, _EMBEDDED
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-FILTER-006",
            "PDF-FILTER",
            "duplicates-retained",
            "filter",
            "With --keep-duplicates, both rows sharing a QR value are retained.",
            "pdf_to_scouts.main line 562 keep_duplicates guard",
        ),
        (
            _embedded(NAME_A, "Youth", URL_A),
            _embedded(NAME_B, "Youth", URL_A),
        ),
        ("--keep-duplicates",),
        PdfObservation(
            attendees=(
                ExtractedAttendeeObservation(
                    NAME_A, NAME_A, "Youth", URL_A, "PDF-FILTER-006.pdf", 1, _EMBEDDED
                ),
                ExtractedAttendeeObservation(
                    NAME_B, NAME_B, "Youth", URL_A, "PDF-FILTER-006.pdf", 2, _EMBEDDED
                ),
            ),
            relative_files=("out.csv",),
        ),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-SCHEMA: exact CSV headers. Members map to pdf_to_scouts.write_attendees_csv /
# write_errors_csv fieldname lists.
# --------------------------------------------------------------------------------------------
_ATTENDEE_COLUMNS = (
    "Attendee Name",
    "Registrant Type",
    "QR Code Contents",
    "Name as Printed",
    "Source PDF",
    "PDF Page",
    "QR Decode Method",
)
_ERROR_COLUMNS = ("Source PDF", "PDF Page", "Attendee Name", "Registrant Type", "Error")

_SCHEMA_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-SCHEMA-001",
            "PDF-SCHEMA",
            "attendee-columns",
            "schema",
            "The attendee CSV header is exactly the seven-column contract.",
            "pdf_to_scouts.write_attendees_csv lines 469-477",
        ),
        (_embedded(NAME_A, "Youth"),),
        (),
        PdfObservation(stdout=_ATTENDEE_COLUMNS),
    ),
    PdfCase(
        _meta(
            "PDF-SCHEMA-002",
            "PDF-SCHEMA",
            "error-columns",
            "schema",
            "The error CSV header is exactly the five-column contract.",
            "pdf_to_scouts.write_errors_csv line 498",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "none"),),
        ("--render-dpi", "72"),
        PdfObservation(stdout=_ERROR_COLUMNS),
    ),
)


# --------------------------------------------------------------------------------------------
# PDF-CLI: main's process contract -- usage, discovery failure, DPI bounds, success, strict,
# quiet, and stale-error removal. Members map to pdf_to_scouts.main return-code and print paths.
# --------------------------------------------------------------------------------------------
_CLI_CASES: tuple[PdfCase, ...] = (
    PdfCase(
        _meta(
            "PDF-CLI-001",
            "PDF-CLI",
            "help",
            "cli",
            "The --help flag prints usage and exits zero without processing any input.",
            "pdf_to_scouts.parse_args argparse --help",
        ),
        (),
        ("--help",),
        PdfObservation(return_code=0, stdout=("usage",)),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-002",
            "PDF-CLI",
            "no-match",
            "cli",
            "Inputs that match no PDF exit 2 with a bounded stderr message.",
            "pdf_to_scouts.main lines 522-524",
        ),
        (),
        ("{missing}", "-o", "{out}"),
        PdfObservation(
            return_code=2,
            stderr=("No PDF files matched the supplied inputs.",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-003",
            "PDF-CLI",
            "dpi-low",
            "cli",
            "A render DPI below the accepted floor exits 2 before any extraction.",
            "pdf_to_scouts.main lines 526-529",
        ),
        (_embedded(NAME_A, "Youth"),),
        ("{pdf}", "-o", "{out}", "--render-dpi", "50"),
        PdfObservation(
            return_code=2,
            stderr=("--render-dpi values must be between 72 and 1200.",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-004",
            "PDF-CLI",
            "dpi-high",
            "cli",
            "A render DPI above the accepted ceiling exits 2 before any extraction.",
            "pdf_to_scouts.main lines 526-529",
        ),
        (_embedded(NAME_A, "Youth"),),
        ("{pdf}", "-o", "{out}", "--render-dpi", "2000"),
        PdfObservation(
            return_code=2,
            stderr=("--render-dpi values must be between 72 and 1200.",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-005",
            "PDF-CLI",
            "success",
            "cli",
            "A clean run prints its progress and summary lines and exits zero.",
            "pdf_to_scouts.main lines 536-596",
        ),
        (_embedded(NAME_A, "Youth"),),
        ("{pdf}", "-o", "{out}"),
        PdfObservation(
            return_code=0,
            stdout=(
                "Reading <root>/PDF-CLI-005.pdf ...",
                "PDF files: 1",
                "Pages/attendees found: 1",
                "Rows written: 1",
                "QR codes decoded in output: 1",
                "Wrote <root>/out.csv",
            ),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-006",
            "PDF-CLI",
            "strict-exit",
            "cli",
            "Under --strict an extraction warning downgrades the exit code to 1 while still "
            "writing output.",
            "pdf_to_scouts.main lines 594-595",
        ),
        (PdfPageSpec(NAME_A, "Youth", URL_A, "none"),),
        ("{pdf}", "-o", "{out}", "--render-dpi", "72", "--strict"),
        PdfObservation(
            return_code=1,
            stdout=(
                "Reading <root>/PDF-CLI-006.pdf ...",
                "PDF files: 1",
                "Pages/attendees found: 1",
                "Rows written: 1",
                "QR codes decoded in output: 0",
                "Pages with extraction warnings: 1 (<root>/out.errors.csv)",
                "Wrote <root>/out.csv",
            ),
            relative_files=("out.csv", "out.errors.csv"),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-007",
            "PDF-CLI",
            "quiet",
            "cli",
            "Under --quiet only the final output path is printed on success.",
            "pdf_to_scouts.main lines 578-592 quiet guard",
        ),
        (_embedded(NAME_A, "Youth"),),
        ("{pdf}", "-o", "{out}", "--quiet"),
        PdfObservation(
            return_code=0,
            stdout=("Wrote <root>/out.csv",),
            relative_files=("out.csv",),
        ),
    ),
    PdfCase(
        _meta(
            "PDF-CLI-008",
            "PDF-CLI",
            "stale",
            "stale",
            "A later clean run removes the stale error CSV left by an earlier warning run.",
            "pdf_to_scouts.main lines 571-575 stale removal",
        ),
        (_embedded(NAME_A, "Youth"),),
        (),
        PdfObservation(
            return_code=0,
            relative_files=("out.csv",),
        ),
    ),
)


PDF_CASES: tuple[PdfCase, ...] = (
    *_DISC_CASES,
    *_ID_CASES,
    *_CASE_CASES,
    *_QR_CASES,
    *_PAGE_CASES,
    *_CORRUPT_CASES,
    *_DEBUG_CASES,
    *_FILTER_CASES,
    *_SCHEMA_CASES,
    *_CLI_CASES,
)
