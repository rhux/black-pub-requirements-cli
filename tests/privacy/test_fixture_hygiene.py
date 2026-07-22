from pathlib import Path

from tools.check_private_data import scan_corpus, scan_patterns

# Build the sentinel token dynamically so this test FILE contains no live-token literal —
# otherwise the Verify step (`check_private_data.py tests`) would flag its own source.
_MOBILE = "scoutingevent.com/" + "mobile"
_LIVE = "REAL" + "TOKEN123"


def test_clean_fixtures_have_no_pattern_findings():
    assert scan_patterns([Path("tests/fixtures"), Path("tests/factories")]) == []


def test_pattern_flags_a_live_token(tmp_path):
    (tmp_path / "leak.json").write_text(f"url: https://{_MOBILE}/?t={_LIVE}", encoding="utf-8")
    assert scan_patterns([tmp_path])


def test_corpus_flags_a_real_name_in_contents(tmp_path):
    (tmp_path / "leak.md").write_text("notes about Ann Leeson", encoding="utf-8")
    findings = scan_corpus([tmp_path], names={"Ann Leeson"}, ids=set())
    # Findings must never echo the matched value, in path OR reason.
    assert findings and all("Ann Leeson" not in f"{path} {reason}" for path, reason in findings)


def test_corpus_flags_a_substring_name(tmp_path):
    """'Ann Lee' must still be caught when embedded in other text."""
    (tmp_path / "leak.md").write_text("Ann Leeson met Ann Lee", encoding="utf-8")
    assert scan_corpus([tmp_path], names={"Ann Lee"}, ids=set())


def test_corpus_flags_an_id_in_a_filename_without_echoing_it(tmp_path):
    leak_id = "88" + "880001"                       # not a literal, and synthetic anyway
    (tmp_path / f"{leak_id}-report.html").write_text(f'<tr data-attendee="{leak_id}">', encoding="utf-8")
    findings = scan_corpus([tmp_path], names=set(), ids={leak_id})
    assert findings                                  # matched (filename + attribute)
    assert all(leak_id not in f"{path} {reason}" for path, reason in findings)   # redacted


def test_corpus_flags_a_surname_fragment(tmp_path):
    (tmp_path / "leak.md").write_text("a note mentioning Leeson somewhere", encoding="utf-8")
    assert scan_corpus([tmp_path], names={"Ann Leeson"}, ids=set())


def test_clean_content_has_no_corpus_findings(tmp_path):
    (tmp_path / "ok.md").write_text("Avery Archer is synthetic", encoding="utf-8")
    assert scan_corpus([tmp_path], names={"Ann Leeson"}, ids={"88" + "880001"}) == []
