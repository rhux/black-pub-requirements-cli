"""ART-HTML-001..005: scoutmb.core.output_schemas.json_for_html's escaping contract. &, <, > are
replaced with \\u0026/\\u003c/\\u003e; U+2028/U+2029 (LINE/PARAGRAPH SEPARATOR, valid inside a
JSON string but invalid inside a raw JavaScript string literal) become \\u2028/\\u2029; every
other character -- including non-ASCII -- passes through literally because json.dumps is called
with ensure_ascii=False. Every case's sentinel/adversarial string still round-trips through
json.loads(json_for_html(...)) back to its ORIGINAL value even though the intermediate text is
HTML/script-safe.
"""

from __future__ import annotations

import json

import pytest

from scoutmb.core.output_schemas import json_for_html


def _embed(description: str) -> str:
    """A minimal requirements payload carrying the sentinel/adversarial description, the same
    shape json_for_html is actually called with (report_data["requirements"][i]["description"])."""
    payload = {"requirements": [{"description": description}]}
    return json_for_html(payload)


@pytest.mark.matrix_case(case_id="ART-HTML-001", context_id="html", lane="default")
def test_xss_sentinel_angle_brackets_escaped_and_round_trips():
    description = "<img src=x onerror=alert(1)>"
    embedded = _embed(description)

    assert "<img" not in embedded
    assert "\\u003cimg" in embedded
    assert "\\u003e" in embedded
    assert "<" not in embedded and ">" not in embedded

    round_tripped = json.loads(embedded)
    assert round_tripped["requirements"][0]["description"] == description


@pytest.mark.matrix_case(case_id="ART-HTML-002", context_id="html", lane="default")
def test_script_close_tag_literal_sequence_never_survives():
    description = "close it here: </script><script>evil()</script>"
    embedded = _embed(description)

    # The literal 4-character sequence '</script>' (in any case) must never appear, so the
    # page's real <script id="report-data"> block cannot be closed early by embedded data.
    assert "</script>" not in embedded
    assert "</script>" not in embedded.lower()
    assert "<" not in embedded and ">" not in embedded

    round_tripped = json.loads(embedded)
    assert round_tripped["requirements"][0]["description"] == description


@pytest.mark.matrix_case(case_id="ART-HTML-003", context_id="html", lane="default")
def test_angle_and_ampersand_all_escaped_and_round_trip():
    description = "A & B <C> D"
    embedded = _embed(description)

    assert "&" not in embedded
    assert "<" not in embedded
    assert ">" not in embedded
    assert "\\u0026" in embedded
    assert "\\u003c" in embedded
    assert "\\u003e" in embedded

    round_tripped = json.loads(embedded)
    assert round_tripped["requirements"][0]["description"] == description


@pytest.mark.matrix_case(case_id="ART-HTML-004", context_id="html", lane="default")
def test_line_and_paragraph_separators_escaped_and_round_trip():
    description = "line one\u2028line two\u2029paragraph two"
    embedded = _embed(description)

    assert "\u2028" not in embedded  # no literal U+2028 survives in the embedded text
    assert "\u2029" not in embedded  # no literal U+2029 survives in the embedded text
    assert "\\u2028" in embedded
    assert "\\u2029" in embedded

    round_tripped = json.loads(embedded)
    assert round_tripped["requirements"][0]["description"] == description


@pytest.mark.matrix_case(case_id="ART-HTML-005", context_id="html", lane="default")
def test_non_ascii_unicode_passes_through_literally_and_round_trips():
    description = "Café 徽章 \U0001f9ed"
    embedded = _embed(description)

    # ensure_ascii=False: non-ASCII characters appear LITERALLY, never as \uXXXX escapes.
    assert description in embedded
    assert "\\u00e9" not in embedded.lower()  # é not escaped
    assert "\\u5fbd" not in embedded.lower()  # 徽 not escaped

    round_tripped = json.loads(embedded)
    assert round_tripped["requirements"][0]["description"] == description
