import json

from tools.verify_corpus import number_shape, summarize_run


def test_number_shape_collapses_values():
    assert number_shape("#3b") == "#Na"
    assert number_shape("#2.Option.A.(1)") == "#N.Aaaaaa.A.(N)"


def test_summary_emits_only_aggregates(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "avery-archer-sched.json").write_text(json.dumps({
        "status": {"status": 1}, "data": [{
            "REQ_NBR_WEB_DISPLAY": "#3b", "REQ_DESCR": "Avery secret text",
            "COMPLETED_REQ_FLAG": "1", "COMPLETED_CLASS_FLAG": "0"}]}), encoding="utf-8")
    summary = summarize_run(tmp_path)
    blob = json.dumps(summary)
    assert summary["requirements"] == 1
    assert summary["flag_combos"]["('1', '0')"] == 1
    assert "Avery" not in blob and "secret" not in blob
