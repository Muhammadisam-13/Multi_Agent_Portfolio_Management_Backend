import json
from pathlib import Path

import pytest

from mizan.data.snapshot import write_snapshot
from mizan.retrieval.bundle import load_items
from mizan.retrieval.evaluate import main, write_report_if_changed

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def snap(tmp_path):
    return write_snapshot(load_items(FIXTURES / "evidence_items.jsonl"), tmp_path / "snaps" / "t1")


def test_runs_the_gold_set_and_prints_scores_and_misses(snap, capsys):
    assert main(["--snapshot", str(snap), "--gold", str(FIXTURES / "gold_queries.json")]) == 0
    out = capsys.readouterr().out
    assert "10 queries" in out and "recall@5 = 0.70" in out and "MRR = 0.70" in out
    assert "MISS q07" in out and "wanted" in out                    # the 3 known vocabulary misses are listed


def test_report_is_written_once_and_left_alone_when_scores_do_not_change(snap, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("mizan.retrieval.evaluate.ROOT", tmp_path)
    args = ["--snapshot", str(snap), "--gold", str(FIXTURES / "gold_queries.json"), "--write-report"]
    assert main(args) == 0 and "wrote" in capsys.readouterr().out
    report = tmp_path / "reports" / "bm25_gold_t1.json"
    first = report.read_text(encoding="utf-8")
    assert json.loads(first)["snapshot"] == "t1"
    assert main(args) == 0 and "unchanged" in capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == first


def test_write_report_if_changed_detects_a_change(tmp_path):
    path = tmp_path / "r.json"
    assert write_report_if_changed(path, {"a": 1}) is True
    assert write_report_if_changed(path, {"a": 1}) is False
    assert write_report_if_changed(path, {"a": 2}) is True


def test_gold_answer_outside_the_bundle_is_reported_not_crashed(snap, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"as_of": "2025-06-30", "queries": [
        {"id": "x", "ticker": "AAA", "query": "loss", "relevant": ["AAA-ANN-2025-07-15"]}]}), encoding="utf-8")
    assert main(["--snapshot", str(snap), "--gold", str(bad)]) == 1
    assert "EVALUATION NOT RUN" in capsys.readouterr().err


def test_tampered_snapshot_or_missing_gold_file_is_refused(snap, tmp_path, capsys):
    assert main(["--snapshot", str(snap), "--gold", str(tmp_path / "nope.json")]) == 1
    (snap / "items.jsonl").write_bytes(b"{}\n")
    assert main(["--snapshot", str(snap), "--gold", str(FIXTURES / "gold_queries.json")]) == 1
    assert "EVALUATION NOT RUN" in capsys.readouterr().err


def test_scores_are_grouped_by_difficulty_when_the_gold_file_has_labels(snap, tmp_path, capsys):
    gold = json.loads((FIXTURES / "gold_queries.json").read_text(encoding="utf-8"))
    for q in gold["queries"]:
        q["difficulty"] = "easy" if q["id"] in ("q01", "q02", "q03") else "hard"
    labelled = tmp_path / "labelled.json"
    labelled.write_text(json.dumps(gold), encoding="utf-8")
    assert main(["--snapshot", str(snap), "--gold", str(labelled)]) == 0
    out = capsys.readouterr().out
    assert "easy     3 queries   recall@5 = 1.00" in out and "hard     7 queries" in out
