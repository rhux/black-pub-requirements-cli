"""Read-only corpus characterization.

Synthetic rows (CORP-FP/READ/MODE/SNAPSHOT-002) run everywhere against tmp trees. The
authentic rows (CORP-CANON-001, CORP-PDF-001, CORP-SNAPSHOT-001) are marked ``private_corpus``,
require a real ``--corpus-dir`` (default ``raw_data``), fingerprint the tree before and after to
prove read-only access, and assert only aggregate counts — never a private path, name, value,
token, or hash. They skip automatically when the corpus is absent (unless ``--require-corpus``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.verify_corpus import summarize_run

from tests.factories.payloads import requirement_row, schedule_payload
from tests.harnesses.corpus import (
    UnreadableCorpusEntry,
    UnsafeCorpusEntry,
    canonical_run_dirs,
    corpus_status,
    extract_pdf_aggregate,
    find_single_pdf,
    fingerprint_tree,
    raw_multisets_all_match,
    raw_payload_multiset,
)


# ------------------------------------------------------------------ synthetic helpers ---
def _write_run(root: Path, name: str, payloads: list[list[object]]) -> Path:
    raw = root / name / "raw"
    raw.mkdir(parents=True)
    for i, rows in enumerate(payloads):
        (raw / f"p{i}.json").write_text(json.dumps({"data": rows}), encoding="utf-8")
    return root / name


# ============================================================== CORP-FP-001 / 002 =======
@pytest.mark.matrix_case(case_id="CORP-FP-001", context_id="corpus", lane="default")
def test_fp_001_unchanged_content_compares_equal(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world", encoding="utf-8")
    assert fingerprint_tree(tmp_path) == fingerprint_tree(tmp_path)


@pytest.mark.matrix_case(case_id="CORP-FP-002", context_id="corpus", lane="default")
def test_fp_002_one_changed_byte_compares_unequal(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello", encoding="utf-8")
    before = fingerprint_tree(tmp_path)
    target.write_text("hallo", encoding="utf-8")
    after = fingerprint_tree(tmp_path)
    assert before != after
    # Neither the fingerprint nor its digest exposes the path or the raw bytes.
    rendered = repr(before) + repr(after) + before.digest() + after.digest()
    assert str(target) not in rendered
    assert "hello" not in rendered and "hallo" not in rendered


# ============================================================== CORP-FP-003 ==============
@pytest.mark.matrix_case(case_id="CORP-FP-003", context_id="corpus", lane="default")
def test_fp_003_symlink_raises_unsafe(tmp_path):
    (tmp_path / "real.txt").write_text("x", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    with pytest.raises(UnsafeCorpusEntry):
        fingerprint_tree(tmp_path)


# ============================================================== CORP-FP-004 ==============
@pytest.mark.matrix_case(case_id="CORP-FP-004", context_id="corpus", lane="default")
def test_fp_004_timestamp_and_mode_changes_do_not_alter_fingerprint(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello", encoding="utf-8")
    before = fingerprint_tree(tmp_path)
    import os

    os.utime(target, (0, 0))  # change mtime/atime
    target.chmod(0o600)  # change mode
    after = fingerprint_tree(tmp_path)
    assert before == after


# ============================================================== CORP-READ-001 ===========
@pytest.mark.matrix_case(case_id="CORP-READ-001", context_id="corpus", lane="default")
def test_read_001_injected_permission_error_becomes_unreadable(tmp_path):
    (tmp_path / "secret-name.txt").write_text("private", encoding="utf-8")

    def deny(_path: Path) -> bytes:
        raise PermissionError(13, "Permission denied", str(tmp_path / "secret-name.txt"))

    with pytest.raises(UnreadableCorpusEntry) as excinfo:
        fingerprint_tree(tmp_path, read_bytes=deny)
    message = str(excinfo.value)
    assert message == "permission-denied"  # reason code only
    assert "secret-name" not in message and str(tmp_path) not in message


# ============================================================== CORP-READ-002 ===========
def test_read_002_malformed_payload_redacts_path(tmp_path):
    raw = tmp_path / "run-1" / "raw"
    raw.mkdir(parents=True)
    bad = raw / "secret-scout-id.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(UnreadableCorpusEntry) as excinfo:
        raw_payload_multiset(tmp_path / "run-1")
    message = str(excinfo.value)
    assert message == "read-error"  # reason code only, not the JSONDecodeError text
    assert "secret-scout-id" not in message and str(tmp_path) not in message


def test_read_002_unreadable_payload_redacts_path(tmp_path, monkeypatch):
    raw = tmp_path / "run-1" / "raw"
    raw.mkdir(parents=True)
    (raw / "secret-scout-id.json").write_text('{"data": []}', encoding="utf-8")

    def deny(_self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(raw / "secret-scout-id.json"))

    monkeypatch.setattr(Path, "read_text", deny)
    with pytest.raises(UnreadableCorpusEntry) as excinfo:
        raw_payload_multiset(tmp_path / "run-1")
    message = str(excinfo.value)
    assert message == "permission-denied"
    assert "secret-scout-id" not in message and str(tmp_path) not in message


# ============================================================== CORP-PDF-002 ============
def test_pdf_002_open_failure_redacts_path(tmp_path):
    pytest.importorskip("fitz")  # aggregate extraction needs the optional PDF stack
    bogus = tmp_path / "secret-attendee-roster.pdf"
    bogus.write_bytes(b"not a real pdf")  # PyMuPDF raises with the real path embedded

    with pytest.raises(UnreadableCorpusEntry) as excinfo:
        extract_pdf_aggregate(bogus)
    message = str(excinfo.value)
    assert message in {"read-error", "permission-denied"}
    assert "secret-attendee-roster" not in message and str(tmp_path) not in message


# ============================================================== CORP-SNAPSHOT-002 ========
@pytest.mark.matrix_case(case_id="CORP-SNAPSHOT-002", context_id="corpus", lane="default")
def test_snapshot_002_changed_payload_breaks_multiset_equality(tmp_path):
    schedule = schedule_payload()["data"][0]
    _write_run(tmp_path, "run-1", [[schedule], [requirement_row()]])
    _write_run(tmp_path, "run-2", [[schedule], [requirement_row(REQ_NBR_WEB_DISPLAY="#9z")]])
    runs = canonical_run_dirs(tmp_path)
    assert len(runs) == 2
    assert raw_payload_multiset(runs[0]) != raw_payload_multiset(runs[1])
    assert raw_multisets_all_match(tmp_path) is False


def test_snapshot_002_identical_runs_match(tmp_path):
    schedule = schedule_payload()["data"][0]
    _write_run(tmp_path, "run-1", [[schedule], [requirement_row()]])
    _write_run(tmp_path, "run-2", [[schedule], [requirement_row()]])
    assert raw_multisets_all_match(tmp_path) is True


# ============================================================== CORP-MODE-001..004 ======
@pytest.mark.matrix_case(case_id="CORP-MODE-001", context_id="corpus", lane="default")
def test_mode_001_absent_corpus_status(tmp_path):
    assert corpus_status(tmp_path / "missing") == "absent"


@pytest.mark.matrix_case(case_id="CORP-MODE-002", context_id="corpus", lane="default")
def test_mode_002_present_corpus_status(tmp_path):
    _write_run(tmp_path, "run-1", [[requirement_row()]])
    assert corpus_status(tmp_path) == "ok"


@pytest.mark.matrix_case(case_id="CORP-MODE-003", context_id="corpus", lane="default")
def test_mode_003_empty_and_wrong_layout_status(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert corpus_status(empty) == "empty"
    wrong = tmp_path / "wrong"
    (wrong / "not-a-run").mkdir(parents=True)
    assert corpus_status(wrong) == "wrong-layout"


@pytest.mark.matrix_case(case_id="CORP-MODE-004", context_id="corpus", lane="default")
def test_mode_004_alternate_root_selected(tmp_path):
    alt = tmp_path / "alternate-root"
    _write_run(alt, "run-1", [[requirement_row()]])
    assert corpus_status(alt) == "ok"
    assert canonical_run_dirs(alt) == [alt / "run-1"]


# ============================================================== authentic fixture ========
@pytest.fixture
def authentic_corpus(pytestconfig: pytest.Config) -> Path:
    corpus_dir = Path(pytestconfig.getoption("--corpus-dir"))
    if corpus_status(corpus_dir) != "ok":
        # --require-corpus already turned absence into a usage error at configure time.
        pytest.skip("private corpus unavailable")
    return corpus_dir


# ============================================================== CORP-CANON-001 ===========
@pytest.mark.private_corpus
@pytest.mark.matrix_case(case_id="CORP-CANON-001", context_id="corpus", lane="authentic")
def test_canon_001_canonical_payload_split(authentic_corpus: Path):
    before = fingerprint_tree(authentic_corpus)
    runs = canonical_run_dirs(authentic_corpus)
    assert runs, "expected at least one run directory"
    summary = summarize_run(runs[0])  # one canonical snapshot; runs are equivalent copies
    after = fingerprint_tree(authentic_corpus)
    assert before == after  # read-only access proven

    assert summary["raw_payloads"] == 120
    assert summary["schedule_payloads"] == 22
    assert summary["requirement_payloads"] == 98
    assert summary["schedule_rows"] == 103
    assert summary["requirement_rows"] == 4858
    assert summary["data_rows"] == 4961
    assert summary["unrecognized_rows"] == 0
    assert summary["deduped_classes"] == 98
    assert summary["requirement_schemas"] == 1
    assert len(summary["number_shapes"]) == 26
    assert len(summary["flag_combos"]) == 4
    assert len(summary["type_marginals"]) == 3
    assert summary["empty_display_rows"] == 31
    assert summary["note_rows"] == 125


# ============================================================== CORP-SNAPSHOT-001 ========
@pytest.mark.private_corpus
@pytest.mark.matrix_case(case_id="CORP-SNAPSHOT-001", context_id="corpus", lane="authentic")
def test_snapshot_001_three_runs_share_multiset(authentic_corpus: Path):
    before = fingerprint_tree(authentic_corpus)
    assert raw_multisets_all_match(authentic_corpus)
    after = fingerprint_tree(authentic_corpus)
    assert before == after


# ============================================================== CORP-PDF-001 ============
@pytest.mark.private_corpus
@pytest.mark.matrix_case(case_id="CORP-PDF-001", context_id="corpus", lane="authentic")
def test_pdf_001_pdf_extraction_aggregate(authentic_corpus: Path):
    before = fingerprint_tree(authentic_corpus)
    pdf = find_single_pdf(authentic_corpus)
    aggregate = extract_pdf_aggregate(pdf)
    after = fingerprint_tree(authentic_corpus)
    assert before == after

    assert aggregate.source_pdfs == 1
    assert aggregate.pages == 26
    assert aggregate.attendees == 26
    assert aggregate.errors == 0
    assert aggregate.embedded_decodes == 26
    assert aggregate.rendered_decodes == 0
