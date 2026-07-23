"""Deterministic input-file builders for the legacy input matrix.

Each builder writes exactly one file below its supplied ``path`` (or, for the workbook
builder, below the parent directory of ``path``) and returns that path. No builder reaches
the network or imports the legacy application. Synthetic identities only -- the row defaults
use ``Avery Example`` / ``Bailey Example`` and ``?t=TESTTOKEN_*`` tokens so nothing here can
resemble real scout data.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook

URL_A = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_A"
URL_B = "https://scoutingevent.com/mobile/checkin?t=TESTTOKEN_B"


@dataclass(frozen=True, slots=True)
class SyntheticInputRow:
    name: str = "Avery Example"
    url: str = URL_A
    registrant_type: str = "Youth"


def write_csv_input(
    path: Path, headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def write_xlsx_input(
    path: Path,
    sheets: Sequence[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]]],
) -> Path:
    """Write a workbook with the given ordered sheets.

    ``sheets`` is a sequence of ``(title, headers, rows)``. An empty sequence writes a
    workbook whose single default sheet has no rows (the "empty workbook" fixture).
    """
    workbook = Workbook()
    default_sheet = workbook.active
    if not sheets:
        workbook.save(path)
        return path
    workbook.remove(default_sheet)
    for title, headers, rows in sheets:
        sheet = workbook.create_sheet(title=title)
        if headers:
            sheet.append(list(headers))
        for row in rows:
            sheet.append(list(row))
    workbook.save(path)
    return path


def write_json_input(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def write_text_input(path: Path, lines: tuple[str, ...]) -> Path:
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
