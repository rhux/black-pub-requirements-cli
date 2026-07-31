"""Where published report/email artifacts go.

One implementation exists today (the filesystem, via adapters/files/atomic.py's
AtomicFileSink); the port exists so the reporting feature can be exercised and reasoned about
without importing that adapter directly -- the architecture test enforces the "features imports
ports only" rule that makes this seam real rather than decorative.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ArtifactSink(Protocol):
    """Where published artifacts go. One implementation today (the filesystem); the port
    exists because the reporting feature must not import the atomic adapter."""

    def publish_text(self, path: Path, content: str, *, encoding: str = "utf-8-sig") -> None: ...
    def publish_rows(self, path: Path, rows: list[Any], fieldnames: list[str]) -> None: ...


class ReportRenderer(Protocol):
    """Turns the report data mapping into a complete HTML document.

    Satisfied by adapters/html/report.render_report. A Protocol rather than a callable alias
    so the parameter name and return type are part of the contract.
    """

    def __call__(self, report_data: dict[str, Any]) -> str: ...
