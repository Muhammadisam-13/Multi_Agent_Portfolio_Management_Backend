import json
from datetime import date
from pathlib import Path

from mizan.data.snapshot import write_snapshot
from mizan.retrieval.bundle import load_items
from mizan.retrieval.sizing import bundle_size, estimate_tokens, format_table, main

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_items.jsonl"
AS_OF = date(2025, 6, 30)


def test_estimate_rounds_up():
    assert estimate_tokens(10, 4) == 3 and estimate_tokens(12, 3) == 4 and estimate_tokens(0, 4) == 0


def test_bundle_size_counts_only_the_as_of_bundle():
    items = load_items(FIXTURES)
    size = bundle_size(items, "aaa", AS_OF)
    in_bundle = [i for i in items if i.ticker in ("AAA", "MACRO") and i.date <= AS_OF]
    assert size["items"] == len(in_bundle) and size["chars"] == sum(len(i.text) for i in in_bundle)
    assert size["tokens_estimate"]["3_chars_per_token"] >= size["tokens_estimate"]["4_chars_per_token"]
    assert sum(v["items"] for v in size["by_type"].values()) == size["items"]
    assert abs(sum(v["share_of_chars"] for v in size["by_type"].values()) - 1) < 0.01


def test_unknown_ticker_has_only_macro_and_empty_ticker_is_zero():
    items = load_items(FIXTURES)
    assert set(bundle_size(items, "ZZZ", AS_OF)["by_type"]) == {"policy_rate", "inflation", "exchange_rate"}
    assert bundle_size([], "AAA", AS_OF)["chars"] == 0


def test_table_says_whether_the_largest_bundle_fits():
    rows = [bundle_size(load_items(FIXTURES), t, AS_OF) for t in ("AAA", "BBB")]
    text = format_table(rows, context_tokens=(10, 100000))
    assert "DOES NOT FIT in a 10-token" in text and "fits in a 100000-token" in text


def test_cli_prints_and_writes_a_counts_only_report(tmp_path, capsys, monkeypatch):
    snap = write_snapshot(load_items(FIXTURES), tmp_path / "snaps" / "t1")
    monkeypatch.setattr("mizan.retrieval.sizing.ROOT", tmp_path)
    assert main(["--snapshot", str(snap), "--as-of", "2025-06-30", "--write-report"]) == 0
    assert "Bundle sizes, snapshot t1" in capsys.readouterr().out
    report = json.loads((tmp_path / "reports" / "bundle_sizes_t1.json").read_text(encoding="utf-8"))
    assert {b["ticker"] for b in report["bundles"]} == {"AAA", "BBB", "CCC"}
    assert all("text" not in b for b in report["bundles"])


def test_cli_refuses_a_tampered_snapshot(tmp_path, capsys):
    snap = write_snapshot(load_items(FIXTURES), tmp_path / "snaps" / "t1")
    (snap / "items.jsonl").write_bytes(b"{}\n")
    assert main(["--snapshot", str(snap), "--as-of", "2025-06-30"]) == 1
    assert "SNAPSHOT NOT USABLE" in capsys.readouterr().err
