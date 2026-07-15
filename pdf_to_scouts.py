#!/usr/bin/env python3
"""Extract attendee names, registrant types, and QR data from schedule PDFs.

The generated CSV is directly compatible with scout_schedule_cli.py.
"""

from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import cv2
import fitz  # PyMuPDF
import numpy as np


DEFAULT_ADULT_TYPES = {"adult", "part-time adult"}
SCOUTINGEVENT_PREFIX = "https://scoutingevent.com/mobile/"


@dataclass(slots=True)
class ExtractedAttendee:
    attendee_name: str
    name_as_printed: str
    registrant_type: str
    qr_data: str
    source_pdf: str
    pdf_page: int
    qr_decode_method: str


@dataclass(slots=True)
class ExtractionError:
    source_pdf: str
    pdf_page: int
    attendee_name: str
    registrant_type: str
    error: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract attendee names and QR-code contents from one or more class-schedule PDFs "
            "and create a CSV compatible with scout_schedule_cli.py."
        )
    )
    parser.add_argument(
        "pdfs",
        nargs="+",
        help=(
            "PDF files, directories, or glob patterns. Directories include *.pdf files; "
            "add --recursive to search subdirectories."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("scouts.csv"),
        help="Output CSV path (default: scouts.csv).",
    )
    parser.add_argument(
        "--errors-output",
        type=Path,
        help="Error CSV path (default: <output stem>.errors.csv).",
    )
    parser.add_argument(
        "--include-adults",
        action="store_true",
        help="Include Adult and Part-Time Adult registrations. Adults are excluded by default.",
    )
    parser.add_argument(
        "--adult-type",
        action="append",
        default=[],
        metavar="TYPE",
        help=(
            "Additional registrant type to treat as an adult and exclude. May be repeated. "
            "Matching is case-insensitive."
        ),
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search directories recursively for PDF files.",
    )
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Keep duplicate QR values encountered across PDFs. By default the first is retained.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with an error if any page is missing a name, registrant type, or decodable QR code.",
    )
    parser.add_argument(
        "--scoutingevent-only",
        action="store_true",
        help=f"Only retain QR values beginning with {SCOUTINGEVENT_PREFIX}",
    )
    parser.add_argument(
        "--no-normalize-obvious-case",
        action="store_true",
        help='Preserve suspicious capitalization such as "MIles" instead of normalizing it to "Miles".',
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        action="append",
        metavar="DPI",
        help=(
            "Fallback page-render DPI. May be repeated. Defaults to 144, 200, 300, and 400. "
            "Embedded QR images are attempted first."
        ),
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        help="Save rendered page images for QR failures to this directory.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors and the final output path.",
    )
    return parser.parse_args(argv)


def expand_pdf_inputs(values: Iterable[str], recursive: bool) -> list[Path]:
    discovered: list[Path] = []

    for raw_value in values:
        expanded = Path(raw_value).expanduser()

        if expanded.is_file():
            if expanded.suffix.lower() == ".pdf":
                discovered.append(expanded.resolve())
            continue

        if expanded.is_dir():
            iterator = expanded.rglob("*.pdf") if recursive else expanded.glob("*.pdf")
            discovered.extend(path.resolve() for path in iterator if path.is_file())
            continue

        # Windows shells commonly do not expand globs, so handle them here.
        matches = glob.glob(str(expanded), recursive=recursive)
        for match in matches:
            path = Path(match)
            if path.is_file() and path.suffix.lower() == ".pdf":
                discovered.append(path.resolve())
            elif path.is_dir():
                iterator = path.rglob("*.pdf") if recursive else path.glob("*.pdf")
                discovered.extend(item.resolve() for item in iterator if item.is_file())

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(discovered, key=lambda item: str(item).lower()):
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def normalized_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def value_after_label(lines: list[str], label: str) -> str:
    wanted = normalized_label(label)
    for index, line in enumerate(lines):
        if normalized_label(line) != wanted:
            continue
        for candidate in lines[index + 1 :]:
            candidate = candidate.strip()
            if candidate:
                return candidate
    return ""


def extract_page_identity(page: fitz.Page) -> tuple[str, str]:
    lines = [line.strip() for line in page.get_text("text").splitlines() if line.strip()]
    attendee_name = value_after_label(lines, "Attendee Information")
    registrant_type = value_after_label(lines, "Registrant")
    return attendee_name, registrant_type


def normalize_obvious_case(name: str) -> str:
    """Fix a narrow class of obvious OCR/source typos without title-casing valid names.

    Example: MIles -> Miles. Names such as McDonald, DeMarco, O'Neil, and AJ remain unchanged.
    """

    def normalize_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if len(token) >= 3 and token[0].isupper() and token[1].isupper() and token[2:].islower():
            return token[0] + token[1:].lower()
        return token

    return re.sub(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", normalize_token, name)


def add_quiet_zone(image: np.ndarray, border: int | None = None) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    border_size = border if border is not None else max(12, min(image.shape[:2]) // 8)
    return cv2.copyMakeBorder(
        image,
        border_size,
        border_size,
        border_size,
        border_size,
        cv2.BORDER_CONSTANT,
        value=255,
    )


def decode_variants(image: np.ndarray, detector: cv2.QRCodeDetector) -> list[str]:
    if image is None or image.size == 0:
        return []

    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    gray = np.ascontiguousarray(gray)
    variants: list[np.ndarray] = [gray]

    try:
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(otsu)
    except cv2.error:
        pass

    decoded: list[str] = []
    seen: set[str] = set()

    for variant in variants:
        with_border = add_quiet_zone(variant)
        for scale in (1, 2, 4, 6):
            candidate = (
                with_border
                if scale == 1
                else cv2.resize(
                    with_border,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_NEAREST,
                )
            )

            try:
                value, _, _ = detector.detectAndDecode(candidate)
                if value and value not in seen:
                    decoded.append(value)
                    seen.add(value)
            except cv2.error:
                pass

            # Detect multiple symbols where supported. This also helps on rendered full pages.
            try:
                ok, values, _, _ = detector.detectAndDecodeMulti(candidate)
                if ok:
                    for value in values:
                        if value and value not in seen:
                            decoded.append(value)
                            seen.add(value)
            except (cv2.error, ValueError):
                pass

            if decoded:
                return decoded

    return decoded


def choose_qr_value(values: Iterable[str]) -> str:
    candidates = [value.strip() for value in values if value and value.strip()]
    if not candidates:
        return ""
    for value in candidates:
        if value.startswith(SCOUTINGEVENT_PREFIX):
            return value
    return candidates[0]


def decode_embedded_qr(
    document: fitz.Document,
    page: fitz.Page,
    detector: cv2.QRCodeDetector,
) -> tuple[str, str]:
    candidates: list[tuple[int, int, int]] = []
    seen_xrefs: set[int] = set()

    for image_info in page.get_images(full=True):
        xref = int(image_info[0])
        width = int(image_info[2])
        height = int(image_info[3])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        # QR codes are normally square. Allow some tolerance for unusual encoders.
        if min(width, height) < 70 or max(width, height) > 2500:
            continue
        if abs(width - height) > max(12, int(max(width, height) * 0.12)):
            continue
        candidates.append((xref, width, height))

    # Smaller, square monochrome images are usually the QR rather than page artwork.
    candidates.sort(key=lambda item: (abs(item[1] - item[2]), item[1] * item[2]))

    for xref, _, _ in candidates:
        try:
            extracted = document.extract_image(xref)
            raw = np.frombuffer(extracted["image"], dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
        except (KeyError, ValueError, cv2.error):
            continue

        values = decode_variants(image, detector)
        selected = choose_qr_value(values)
        if selected:
            return selected, f"embedded-image:xref-{xref}"

    return "", ""


def page_regions(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    height, width = image.shape[:2]
    regions: list[tuple[str, np.ndarray]] = [("full-page", image)]

    # Schedules typically place the QR in the upper-right, but include every quadrant.
    regions.extend(
        [
            ("upper-right", image[0 : int(height * 0.45), int(width * 0.55) : width]),
            ("upper-left", image[0 : int(height * 0.45), 0 : int(width * 0.45)]),
            ("lower-right", image[int(height * 0.50) : height, int(width * 0.50) : width]),
            ("lower-left", image[int(height * 0.50) : height, 0 : int(width * 0.50)]),
        ]
    )
    return regions


def render_page(page: fitz.Page, dpi: int) -> np.ndarray:
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8)
    image = image.reshape(pixmap.height, pixmap.width, pixmap.n)
    if pixmap.n == 4:
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    if pixmap.n == 3:
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


def decode_rendered_qr(
    page: fitz.Page,
    detector: cv2.QRCodeDetector,
    dpis: Sequence[int],
) -> tuple[str, str, np.ndarray | None]:
    last_render: np.ndarray | None = None
    for dpi in dpis:
        image = render_page(page, dpi)
        last_render = image
        for region_name, region in page_regions(image):
            values = decode_variants(region, detector)
            selected = choose_qr_value(values)
            if selected:
                return selected, f"rendered:{dpi}dpi:{region_name}", image
    return "", "", last_render


def extract_pdf(
    pdf_path: Path,
    dpis: Sequence[int],
    normalize_case: bool,
    debug_dir: Path | None,
) -> tuple[list[ExtractedAttendee], list[ExtractionError]]:
    attendees: list[ExtractedAttendee] = []
    errors: list[ExtractionError] = []
    detector = cv2.QRCodeDetector()

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises several exception types for malformed PDFs.
        return [], [ExtractionError(pdf_path.name, 0, "", "", f"Could not open PDF: {exc}")]

    with document:
        for page_index, page in enumerate(document, start=1):
            printed_name, registrant_type = extract_page_identity(page)
            attendee_name = normalize_obvious_case(printed_name) if normalize_case else printed_name

            qr_data, decode_method = decode_embedded_qr(document, page, detector)
            failed_render: np.ndarray | None = None
            if not qr_data:
                qr_data, decode_method, failed_render = decode_rendered_qr(page, detector, dpis)

            missing: list[str] = []
            if not printed_name:
                missing.append("attendee name")
            if not registrant_type:
                missing.append("registrant type")
            if not qr_data:
                missing.append("QR code")

            if missing:
                errors.append(
                    ExtractionError(
                        source_pdf=pdf_path.name,
                        pdf_page=page_index,
                        attendee_name=attendee_name,
                        registrant_type=registrant_type,
                        error="Missing " + ", ".join(missing),
                    )
                )
                if debug_dir is not None and not qr_data:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    if failed_render is None:
                        failed_render = render_page(page, max(dpis))
                    debug_name = f"{pdf_path.stem}-page-{page_index:03d}.png"
                    cv2.imwrite(str(debug_dir / debug_name), failed_render)

            if printed_name or registrant_type or qr_data:
                attendees.append(
                    ExtractedAttendee(
                        attendee_name=attendee_name,
                        name_as_printed=printed_name,
                        registrant_type=registrant_type,
                        qr_data=qr_data,
                        source_pdf=pdf_path.name,
                        pdf_page=page_index,
                        qr_decode_method=decode_method,
                    )
                )

    return attendees, errors


def write_attendees_csv(path: Path, attendees: Sequence[ExtractedAttendee]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Attendee Name",
        "Registrant Type",
        "QR Code Contents",
        "Name as Printed",
        "Source PDF",
        "PDF Page",
        "QR Decode Method",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for attendee in attendees:
            writer.writerow(
                {
                    "Attendee Name": attendee.attendee_name,
                    "Registrant Type": attendee.registrant_type,
                    "QR Code Contents": attendee.qr_data,
                    "Name as Printed": attendee.name_as_printed,
                    "Source PDF": attendee.source_pdf,
                    "PDF Page": attendee.pdf_page,
                    "QR Decode Method": attendee.qr_decode_method,
                }
            )


def write_errors_csv(path: Path, errors: Sequence[ExtractionError]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Source PDF", "PDF Page", "Attendee Name", "Registrant Type", "Error"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for error in errors:
            writer.writerow(
                {
                    "Source PDF": error.source_pdf,
                    "PDF Page": error.pdf_page,
                    "Attendee Name": error.attendee_name,
                    "Registrant Type": error.registrant_type,
                    "Error": error.error,
                }
            )


def main(
    argv: Sequence[str] | None = None,
    *,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> int:
    args = parse_args(argv)
    pdf_paths = expand_pdf_inputs(args.pdfs, args.recursive)
    if not pdf_paths:
        print("No PDF files matched the supplied inputs.", file=sys.stderr)
        return 2

    dpis = tuple(dict.fromkeys(args.render_dpi or [144, 200, 300, 400]))
    if any(dpi < 72 or dpi > 1200 for dpi in dpis):
        print("--render-dpi values must be between 72 and 1200.", file=sys.stderr)
        return 2

    adult_types = DEFAULT_ADULT_TYPES | {value.strip().casefold() for value in args.adult_type}
    extracted: list[ExtractedAttendee] = []
    errors: list[ExtractionError] = []

    for index, pdf_path in enumerate(pdf_paths, start=1):
        if not args.quiet:
            print(f"Reading {pdf_path} ...")
        if progress_callback is not None:
            progress_callback(index, len(pdf_paths), pdf_path)
        pdf_attendees, pdf_errors = extract_pdf(
            pdf_path=pdf_path,
            dpis=dpis,
            normalize_case=not args.no_normalize_obvious_case,
            debug_dir=args.debug_dir,
        )
        extracted.extend(pdf_attendees)
        errors.extend(pdf_errors)

    retained: list[ExtractedAttendee] = []
    seen_qr: set[str] = set()
    skipped_adults = 0
    skipped_nonmatching = 0
    skipped_duplicates = 0

    for attendee in extracted:
        if not args.include_adults and attendee.registrant_type.strip().casefold() in adult_types:
            skipped_adults += 1
            continue
        if args.scoutingevent_only and not attendee.qr_data.startswith(SCOUTINGEVENT_PREFIX):
            skipped_nonmatching += 1
            continue
        if attendee.qr_data and not args.keep_duplicates:
            if attendee.qr_data in seen_qr:
                skipped_duplicates += 1
                continue
            seen_qr.add(attendee.qr_data)
        retained.append(attendee)

    write_attendees_csv(args.output, retained)

    errors_output = args.errors_output or args.output.with_name(f"{args.output.stem}.errors.csv")
    if errors:
        write_errors_csv(errors_output, errors)
    elif errors_output.exists():
        errors_output.unlink()

    decoded_count = sum(1 for attendee in retained if attendee.qr_data)
    if not args.quiet:
        print(f"PDF files: {len(pdf_paths)}")
        print(f"Pages/attendees found: {len(extracted)}")
        print(f"Rows written: {len(retained)}")
        print(f"QR codes decoded in output: {decoded_count}")
        if skipped_adults:
            print(f"Adults skipped: {skipped_adults}")
        if skipped_nonmatching:
            print(f"Non-ScoutingEvent QR values skipped: {skipped_nonmatching}")
        if skipped_duplicates:
            print(f"Duplicate QR values skipped: {skipped_duplicates}")
        if errors:
            print(f"Pages with extraction warnings: {len(errors)} ({errors_output})")

    print(f"Wrote {args.output}")

    if args.strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
