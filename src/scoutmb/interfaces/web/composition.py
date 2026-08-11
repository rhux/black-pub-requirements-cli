"""The ONLY module under interfaces/web permitted to import an adapter (mirrors
interfaces/cli/composition.py's convention; enforced by the same architecture test)."""

from __future__ import annotations

from scoutmb.adapters.files.atomic import AtomicFileSink
from scoutmb.adapters.html.report import render_report
from scoutmb.features.reporting.service import ReportingService


def build_reporting_service() -> ReportingService:
    return ReportingService(sink=AtomicFileSink(), renderer=render_report)
