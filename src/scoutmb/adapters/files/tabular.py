"""File-format parsing for attendee inputs. PARSING ONLY.

Selection, normalization, the adult filter, dedup and the empty-result error live in
features/ingest -- adapters parse, features orchestrate. Putting the filter here is what an
earlier draft did and it collapses the seam the port exists to create.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# NOTE: keep this at module scope, not function-local. scout_schedule_cli.py imports
# this module at module scope for its legacy re-export (see the comment there next to
# the `from scoutmb.adapters.files.tabular import ...` block), so an eager, module-scope
# import here reproduces the pre-existing eager-import behavior that the frozen
# IN-IMPORT-003 catalog case (tests/matrix/cases/input_cases.py) depends on --
# specifically that openpyxl is already in sys.modules by the time playwright's
# ImportError fires under the acquisition profile. Moving this inside load_xlsx
# would silently change that case's expected output.
# (IN-IMPORT-004's all profile blocks openpyxl too, so it fails on its own
# import before order/placement matters -- unaffected by this note.)
from openpyxl import load_workbook

from scoutmb.core.models import ScoutInput


class TabularAttendeeSource:
    """AttendeeSource over the four file formats, plus a text fallback for anything else.

    supports() always returns True: load() below has an unconditional else-branch that
    treats any suffix other than .xlsx/.csv/.json as line-delimited text, matching the
    legacy load_inputs's unconditional `else: return load_text(path)`. supports() must
    mirror that -- narrowing it to a fixed suffix set (as an earlier draft did) silently
    made IngestService reject files (e.g. .dat, .tsv) that load() itself already knows
    how to parse.
    """

    def __init__(self, *, sheet_name: str = "Scouts Only") -> None:
        self.sheet_name = sheet_name

    def supports(self, path: Path) -> bool:  # noqa: ARG002 -- part of the AttendeeSource protocol
        return True

    def load(self, path: Path) -> list[ScoutInput]:
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            return load_xlsx(path, self.sheet_name)
        if suffix == ".csv":
            return load_csv(path)
        if suffix == ".json":
            return load_json(path)
        return load_text(path)


def norm_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def first_matching_key(headers: dict[str, int], candidates: Iterable[str]) -> int | None:
    for candidate in candidates:
        key = norm_header(candidate)
        if key in headers:
            return headers[key]
    return None


def load_xlsx(path: Path, sheet_name: str) -> list[ScoutInput]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    if sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
    elif "Scouts Only" in workbook.sheetnames:
        sheet = workbook["Scouts Only"]
    else:
        sheet = workbook[workbook.sheetnames[0]]

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = {norm_header(value): index for index, value in enumerate(rows[0])}
    name_index = first_matching_key(headers, ["Attendee Name", "Name", "Scout Name"])
    url_index = first_matching_key(headers, ["QR Code Contents", "URL", "QR URL", "Link"])
    type_index = first_matching_key(headers, ["Registrant Type", "Type"])
    if url_index is None:
        raise ValueError(f"Could not find a URL column in XLSX sheet {sheet.title!r}")

    result: list[ScoutInput] = []
    for row in rows[1:]:
        url = str(row[url_index] or "")
        name = str(row[name_index] or "") if name_index is not None else ""
        registrant_type = str(row[type_index] or "") if type_index is not None else ""
        result.append(ScoutInput(name=name, url=url, registrant_type=registrant_type))
    return result


def load_csv(path: Path) -> list[ScoutInput]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames:
            header_map = {norm_header(name): name for name in reader.fieldnames}
            url_key = next(
                (
                    header_map[norm_header(name)]
                    for name in ["QR Code Contents", "URL", "QR URL", "Link"]
                    if norm_header(name) in header_map
                ),
                None,
            )
            name_key = next(
                (
                    header_map[norm_header(name)]
                    for name in ["Attendee Name", "Name", "Scout Name"]
                    if norm_header(name) in header_map
                ),
                None,
            )
            type_key = next(
                (
                    header_map[norm_header(name)]
                    for name in ["Registrant Type", "Type"]
                    if norm_header(name) in header_map
                ),
                None,
            )
            if url_key:
                return [
                    ScoutInput(
                        name=(row.get(name_key, "") if name_key else "") or "",
                        url=(row.get(url_key, "") or ""),
                        registrant_type=(row.get(type_key, "") if type_key else "") or "",
                    )
                    for row in reader
                ]

    # Fall back to one URL per line if the CSV does not have recognizable headers.
    return load_text(path)


def load_json(path: Path) -> list[ScoutInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("scouts") or payload.get("data") or [payload]
    result: list[ScoutInput] = []
    for item in payload:
        if isinstance(item, str):
            result.append(ScoutInput(name="", url=item))
        elif isinstance(item, dict):
            result.append(
                ScoutInput(
                    name=str(item.get("name") or item.get("attendee_name") or ""),
                    url=str(
                        item.get("url") or item.get("qr_url") or item.get("qr_code_contents") or ""
                    ),
                    registrant_type=str(item.get("registrant_type") or item.get("type") or ""),
                )
            )
    return result


def load_text(path: Path) -> list[ScoutInput]:
    result: list[ScoutInput] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line and "https://" in line:
            name, url = line.split(",", 1)
            result.append(ScoutInput(name=name.strip(), url=url.strip()))
        else:
            result.append(ScoutInput(name="", url=line))
    return result
