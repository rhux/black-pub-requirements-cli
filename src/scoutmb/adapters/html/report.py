"""Report template loading and rendering.

Resources load through importlib.resources, never Path(__file__).parent: the package is
banned from referencing its own location, and __file__ arithmetic does not survive every
distribution shape. Task 3 proved this works from a wheel AND a copied release root.
"""

from __future__ import annotations

from importlib.resources import files
from typing import Any

from scoutmb.core.output_schemas import json_for_html

_PACKAGE = "scoutmb.resources"


def load_template(name: str) -> str:
    return files(_PACKAGE).joinpath("templates", name).read_text(encoding="utf-8")


def render_report(report_data: dict[str, Any]) -> str:
    """Substitute CSS, then JS, then DATA.

    DATA is LAST and deliberately so: CSS or JS containing the literal token __REPORT_DATA__
    would otherwise be replaced by the payload.
    """
    html = load_template("report.html")
    html = html.replace("__REPORT_CSS__", load_template("report.css"))
    html = html.replace("__REPORT_JS__", load_template("report.js"))
    return html.replace("__REPORT_DATA__", json_for_html(report_data))
