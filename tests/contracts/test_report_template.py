from __future__ import annotations

import json
from pathlib import Path

from scoutmb.adapters.html.report import load_template, render_report


def test_template_loads_without_dunder_file() -> None:
    text = load_template("report.html")
    assert "__REPORT_DATA__" in text, "the injection point must survive in the template itself"


def test_no_report_token_survives_rendering() -> None:
    html = render_report({"scouts": [], "classes": [], "requirements": [], "errors": []})
    assert "__REPORT_DATA__" not in html


def test_script_close_and_line_separators_cannot_break_out() -> None:
    hostile = {
        "scouts": [{"name": "</script><script>alert(1)</script>"}],
        "classes": [],
        "requirements": [],
        "errors": [],
    }
    html = render_report(hostile)
    assert "</script><script>" not in html
    assert " " not in html
    assert " " not in html


def test_rendered_payload_round_trips(tmp_path: Path) -> None:
    payload = {
        "scouts": [{"name": "Avery Example"}],
        "classes": [],
        "requirements": [],
        "errors": [],
    }
    html = render_report(payload)
    start = html.index('<script id="report-data"')
    embedded = html[html.index(">", start) + 1 : html.index("</script>", start)]
    assert json.loads(embedded) == payload
