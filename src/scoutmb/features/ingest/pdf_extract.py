"""Stage-1 (PDF) ingest policy: which paths qualify as input, and the output CSV shape.

Deliberately does NOT import scoutmb.adapters.pdf -- extract_pdf (the page-by-page decode loop)
lives in adapters/pdf/pages.py instead, because it needs cv2/fitz directly (not just the
already-open-object decode functions), and features may not depend on adapters
(tests/architecture's dependency-rule graph). What belongs here is genuinely adapter-independent:
file discovery and CSV-writing policy.

This module no longer defines its own SCOUTINGEVENT_PREFIX -- it moved to scoutmb.core.models,
which scoutmb.adapters.pdf.extract and scoutmb.interfaces.cli.pdf now both import directly.
Keeping two independently-typed copies (one here, one in the adapter) was exactly the drift
Task 16 fixed once already; see Task 18 review finding #2. scoutmb.features.ingest.service's
QR_URL_PREFIX is a separate constant for a separate purpose (URL validation policy for the
tabular source) and is left as-is.
"""

from __future__ import annotations

import csv
import glob
import io
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from scoutmb.core.models import ExtractedAttendee, ExtractionError


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

        # Windows shells commonly do not expand globs, so handle them here. glob.glob (not
        # Path.glob) is needed: `expanded` is an arbitrary user-supplied pattern string that
        # may embed wildcards anywhere, not a base-path-plus-pattern pair Path.glob expects.
        matches = glob.glob(str(expanded), recursive=recursive)  # noqa: PTH207
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


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Render-first, same-dir temp, fsync, atomic replace. A failed write never truncates
    the previous file. (Full D11 contract -- exclusive temp, parent-dir fsync -- is Slice 2.)

    A copy of scout_schedule_cli.py's helper of the same name: this module must not import
    scout_schedule_cli (that would pull Playwright into the PDF stage)."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # noqa: PTH105 - keep os.replace so failure injection works
    finally:
        tmp.unlink(missing_ok=True)


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
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
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
    atomic_write_text(path, buffer.getvalue())


def write_errors_csv(path: Path, errors: Sequence[ExtractionError]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Source PDF", "PDF Page", "Attendee Name", "Registrant Type", "Error"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
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
    atomic_write_text(path, buffer.getvalue())
