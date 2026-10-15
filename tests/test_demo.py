from datetime import date
from pathlib import Path

import pytest

from mizan.data.snapshot import write_snapshot
from mizan.retrieval.bundle import load_items
from mizan.retrieval.demo import build_report, main

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_items.jsonl"
AS_OF = date(2025, 6, 30)


@pytest.fixture
def items():
    return load_items(FIXTURES)


def test_report_shows_the_bundle_and_both_rules(items):
    text = build_report(items, "aaa", AS_OF, "fixtures")
    assert "Bundle for AAA as of 2025-06-30  (fixtures)" in text
    assert "1 AAA items dated after 2025-06-30 were left out (earliest: 2025-07-15  AAA-ANN-2025-07-15)" in text
    assert "items belonging to other tickers were left out; MACRO items included: 3" in text
    assert "AAA-ANN-2025-07-15" not in text.split("Rule 2")[1]                  # the future item is only named as excluded
    assert "tickers in the bundle: ['AAA', 'MACRO']" in text


def test_future_macro_item_never_appears(items):
    assert "MACRO-POLICY-2025-07-20" not in build_report(items, "AAA", AS_OF)


def test_unknown_ticker_gives_an_explained_empty_bundle(items):
    text = build_report(items, "ZZZ", AS_OF)
    assert "no data for ZZZ in this snapshot" in text and "not an error" in text


def test_compare_lists_what_appears_between_two_dates(items):
    text = build_report(items, "AAA", AS_OF, compare_as_of=date(2025, 6, 1))
    assert "Compared with as of 2025-06-01" in text and "added" in text
    assert "AAA-ANN-2025-06-30" in text                                   # dated between the two as-of dates
    assert "AAA-ANN-2025-04-25" not in text.split("Compared with")[1]     # already present on both dates


def test_query_runs_bm25_inside_the_bundle(items):
    text = build_report(items, "AAA", AS_OF, query="dividend")
    assert "BM25 search in this bundle for 'dividend'" in text and "1. score" in text
    assert "no item shares a word" in build_report(items, "AAA", AS_OF, query="cryptocurrency")


def test_cli_verifies_the_snapshot_and_prints(tmp_path, capsys, items):
    snap = write_snapshot(items, tmp_path / "snaps" / "t1")
    assert main(["--snapshot", str(snap), "--ticker", "BBB", "--as-of", "2025-06-30"]) == 0
    assert "Bundle for BBB as of 2025-06-30" in capsys.readouterr().out


def test_cli_refuses_a_tampered_snapshot(tmp_path, capsys, items):
    snap = write_snapshot(items, tmp_path / "snaps" / "t1")
    path = snap / "items.jsonl"
    path.write_bytes(path.read_bytes().replace(b"AAA closed", b"AAA CLOSED"))
    assert main(["--snapshot", str(snap), "--ticker", "AAA", "--as-of", "2025-06-30"]) == 1
    assert "SNAPSHOT NOT USABLE" in capsys.readouterr().err


def test_cli_reports_a_missing_snapshot(tmp_path, capsys):
    assert main(["--snapshot", "nope", "--ticker", "AAA", "--as-of", "2025-06-30",
                 "--snapshots-dir", str(tmp_path)]) == 1
    assert "SNAPSHOT NOT USABLE" in capsys.readouterr().err


def test_budget_shows_what_fits_and_what_was_left_out(items):
    text = build_report(items, "AAA", AS_OF, query="dividend", budget_tokens=100)
    assert "Context for the model: budget 100 tokens (estimate)" in text and "left out:" in text
    assert "AAA-ANN-2025-04-25" in text.split("Context for the model")[1]          # the dividend announcement was kept
    assert "Context for the model" not in build_report(items, "AAA", AS_OF)


def test_cli_can_use_plain_or_normalized_search(tmp_path, capsys, items):
    snap = write_snapshot(items, tmp_path / "snaps" / "t1")
    base = ["--snapshot", str(snap), "--ticker", "AAA", "--as-of", "2025-06-30", "--query", "dividends"]
    assert main(base + ["--retriever", "bm25"]) == 0
    assert "no item shares a word with the query" in capsys.readouterr().out         # plain BM25: "dividends" != "dividend"
    assert main(base) == 0
    assert "1. score" in capsys.readouterr().out                                      # normalized (default): found
