from __future__ import annotations

import json
from pathlib import Path

from scoutmb.adapters.html.report import load_template, render_report


def test_template_loads_without_dunder_file() -> None:
    text = load_template("report.html")
    assert "__REPORT_DATA__" in text, "the injection point must survive in the template itself"


def test_template_file_ends_with_trailing_newline() -> None:
    """The legacy inline `template = r'''...'''` literal in scout_schedule_cli.py (commit
    a063621) ended with `</html>` followed by a newline. The extracted resource file must
    preserve that exact trailing byte -- Task 21's acceptance bar was a pure, byte-identical
    move, and a missing trailing newline is a silent 1-byte drift that no other test here
    catches: the goldens only re-parse the embedded JSON payload, never the raw HTML bytes."""
    from importlib.resources import files

    raw = files("scoutmb.resources").joinpath("templates", "report.html").read_bytes()
    assert raw.endswith(b"</html>\n"), (
        "report.html must end with '</html>\\n' (trailing newline), matching the original "
        "inline template literal byte-for-byte"
    )
    assert not raw.endswith(b"</html>\n\n"), "must not gain an extra blank line either"


def test_rendered_report_ends_with_trailing_newline() -> None:
    """Same contract as above, exercised through the real render_report() substitution
    pipeline (CSS -> JS -> DATA) rather than reading the template file directly."""
    html = render_report({"scouts": [], "classes": [], "requirements": [], "errors": []})
    assert html.endswith("</html>\n")


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
