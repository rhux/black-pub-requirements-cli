"""Stage-1 CLI: extract attendee identity and QR-code data from schedule PDFs.

Interface layer -- argument parsing and orchestration only. This module must never import
scoutmb.adapters.* directly; the real fitz/cv2-backed extractor is obtained through
scoutmb.interfaces.cli.composition.build_pdf_extractor() instead
(tests/architecture's test_adapter_imports_confined_to_composition_roots enforces this).

This is the ``troop349-pdf`` console-script target declared in pyproject.toml.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from scoutmb.core.models import ExtractedAttendee, ExtractionError
from scoutmb.features.ingest.pdf_extract import (
    SCOUTINGEVENT_PREFIX,
    expand_pdf_inputs,
    write_attendees_csv,
    write_errors_csv,
)
from scoutmb.interfaces.cli.composition import build_pdf_extractor

DEFAULT_ADULT_TYPES = {"adult", "part-time adult"}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        # Pinned rather than left to argparse's sys.argv[0]-basename default: the console
        # script (troop349-pdf, 12 chars) and the legacy shim (pdf_to_scouts.py, 16 chars)
        # would otherwise wrap the usage synopsis at different points -- prog length changes
        # where argparse breaks lines -- which is exactly what
        # tests/compat/test_legacy_entrypoints.py's usage-parity check would catch as a
        # mismatch beyond just the program name.
        prog="troop349-pdf",
        description=(
            "Extract attendee names and QR-code contents from one or more class-schedule PDFs "
            "and create a CSV compatible with scout_schedule_cli.py."
        ),
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

    extract_pdf = build_pdf_extractor()

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
