"""Atomic single-file publication (D11) and CSV writing.

ENCODING CONTRACT -- both halves are load-bearing:
  * csv.DictWriter writes into a StringIO with its default lineterminator "\\r\\n";
  * atomic_write_text opens with newline="" so Python does NOT translate it.
Change either and classes.csv / requirements.csv change on disk (ART-SCHEMA-002/003).
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Render-first, same-dir temp, fsync, atomic replace. A failed write never truncates
    the previous file. (Full D11 contract — exclusive temp, parent-dir fsync — is Slice 2.)"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # noqa: PTH105 - the failure test monkeypatches os.replace;
        #                        Path.replace would defeat that injection. Keep os.replace.
    finally:
        tmp.unlink(missing_ok=True)


def write_csv(path: Path, records: list[Any], fieldnames: list[str]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(asdict(record))
    atomic_write_text(path, buffer.getvalue())


class AtomicFileSink:
    """ArtifactSink over atomic_write_text / write_csv."""

    def publish_text(self, path: Path, content: str, *, encoding: str = "utf-8-sig") -> None:
        atomic_write_text(path, content, encoding=encoding)

    def publish_rows(self, path: Path, rows: list[Any], fieldnames: list[str]) -> None:
        write_csv(path, rows, fieldnames)
