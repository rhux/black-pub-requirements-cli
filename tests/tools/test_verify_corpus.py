import json
from pathlib import Path

import pytest
from tests.factories.payloads import requirement_row, schedule_payload
from tools.verify_corpus import (
    classify_row,
    main,
    number_shape,
    summarize_run,
    unrecognized_reason,
)


def write_raw_payload(root: Path, rows: list[object], name: str = "payload.json") -> Path:
    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    path = raw / name
    path.write_text(json.dumps({"data": rows}), encoding="utf-8")
    return path


def test_number_shape_collapses_values():
    assert number_shape("#3b") == "#Na"
    assert number_shape("#2.Option.A.(1)") == "#N.Aaaaaa.A.(N)"


# --- CORP-SPLIT-001 ---------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="CORP-SPLIT-001", context_id="corpus", lane="default")
def test_mixed_payload_partitions_schedule_and_requirement(tmp_path):
    schedule = schedule_payload()["data"][0]
    write_raw_payload(tmp_path, [schedule, requirement_row()])
    summary = summarize_run(tmp_path)
    assert summary["data_rows"] == 2
    assert summary["schedule_rows"] == 1
    assert summary["requirement_rows"] == 1
    assert summary["unrecognized_rows"] == 0
    # Requirement marginals exclude the schedule row.
    assert summary["flag_combos"] == {"('0', '0')": 1}


# --- CORP-SPLIT-002 ---------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="CORP-SPLIT-002", context_id="corpus", lane="default")
def test_requirement_schema_does_not_depend_on_flags(tmp_path):
    row = requirement_row(COMPLETED_REQ_FLAG=None, COMPLETED_CLASS_FLAG=None)
    write_raw_payload(tmp_path, [row])
    summary = summarize_run(tmp_path)
    assert summary["requirement_rows"] == 1
    assert summary["flag_combos"] == {"(None, None)": 1}


# --- CORP-SPLIT-003 ---------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="CORP-SPLIT-003", context_id="corpus", lane="default")
def test_row_matching_both_predicates_is_unrecognized(tmp_path):
    both = {**schedule_payload()["data"][0], **requirement_row()}
    assert classify_row(both) == "unrecognized"
    write_raw_payload(tmp_path, [both])
    summary = summarize_run(tmp_path)
    assert summary["unrecognized_rows"] == 1
    assert summary["schedule_rows"] == 0
    assert summary["requirement_rows"] == 0


def test_both_predicate_reason_is_redacted(tmp_path):
    both = {**schedule_payload()["data"][0], **requirement_row()}
    reason = unrecognized_reason(both)
    assert "extra_field_count" in reason
    # Field VALUES never appear in the reason.
    assert "Chess" not in reason and "Pavilion" not in reason


# --- CORP-SPLIT-004 ---------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="CORP-SPLIT-004", context_id="corpus", lane="default")
def test_non_mapping_row_is_unrecognized_without_echo(tmp_path):
    secret = "avery-secret-token"
    assert classify_row(secret) == "unrecognized"
    reason = unrecognized_reason(secret)
    assert reason == "non-mapping data row (type=str)"
    assert secret not in reason
    write_raw_payload(tmp_path, [secret, 12345])
    summary = summarize_run(tmp_path)
    assert summary["unrecognized_rows"] == 2
    assert secret not in json.dumps(summary["unrecognized_reasons"])


# --- CORP-CLI-001 -----------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="CORP-CLI-001", context_id="corpus", lane="default")
def test_cli_valid_output_exits_zero_and_leaks_nothing(tmp_path, capsys):
    run = tmp_path / "run-a"
    run.mkdir()
    write_raw_payload(run, [schedule_payload()["data"][0], requirement_row()])
    rc = main([str(tmp_path)])
    out = capsys.readouterr()
    assert rc == 0
    assert "data_rows: 2" in out.out
    assert "requirement_rows: 1" in out.out
    # No input directory path and no argparse description in output.
    assert str(tmp_path) not in out.out
    assert "run-a" not in out.out
    assert "Reproduce the design spec" not in out.out


# --- CORP-CLI-002 -----------------------------------------------------------------------
@pytest.mark.matrix_case(case_id="CORP-CLI-002", context_id="corpus", lane="default")
def test_cli_missing_corpus_exits_two_with_one_bounded_line(tmp_path, capsys):
    missing = tmp_path / "does-not-exist"
    rc = main([str(missing)])
    err = capsys.readouterr().err
    assert rc == 2
    assert err.strip().count("\n") == 0  # exactly one line
    assert str(missing) not in err  # path not echoed


def test_require_known_schema_fails_on_unrecognized(tmp_path, capsys):
    run = tmp_path / "run-a"
    run.mkdir()
    write_raw_payload(run, [{"UNEXPECTED_FIELD": "zzsecretvalue"}])
    rc = main([str(tmp_path), "--require-known-schema"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "zzsecretvalue" not in err  # value never echoed
    assert "UNEXPECTED_FIELD" not in err  # unknown field name never echoed
    assert "extra_field_count" in err


def test_summary_emits_only_aggregates(tmp_path):
    write_raw_payload(tmp_path, [requirement_row(REQ_DESCR="Avery secret text")])
    summary = summarize_run(tmp_path)
    blob = json.dumps(summary)
    assert summary["requirement_rows"] == 1
    assert summary["flag_combos"]["('0', '0')"] == 1
    assert "Avery" not in blob and "secret" not in blob


def test_unreadable_payload_is_counted_not_ignored(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "broken.json").write_text("{not json", encoding="utf-8")
    summary = summarize_run(tmp_path)
    assert summary["unreadable_payloads"] == 1
    assert summary["data_rows"] == 0
