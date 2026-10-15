import json
from datetime import date
from pathlib import Path

import pytest

from mizan.data.snapshot import write_snapshot
from mizan.data.tickers import load_tickers
from mizan.retrieval.bundle import load_items
from mizan.retrieval.store import SnapshotError, SnapshotStore, resolve_snapshot_folder

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_items.jsonl"
AS_OF = date(2025, 6, 30)


@pytest.fixture
def folder(tmp_path):
    return write_snapshot(load_items(FIXTURES), tmp_path / "snaps" / "t1")


def test_loads_a_verified_snapshot_and_summarises_it(folder):
    store = SnapshotStore.load(folder)
    summary = store.summary()
    assert summary["name"] == "t1" and summary["verified"] is True and summary["item_count"] == 13
    assert summary["tickers"] == ["AAA", "BBB", "CCC"] and summary["date_range"] == ["2025-03-31", "2025-07-20"]
    assert store.latest_date() == date(2025, 7, 20)


def test_bundle_applies_both_rules(folder):
    store = SnapshotStore.load(folder)
    bundle = store.bundle("aaa", AS_OF)
    assert all(i.date <= AS_OF for i in bundle.items) and {i.ticker for i in bundle.items} == {"AAA", "MACRO"}
    assert "AAA-ANN-2025-07-15" not in {i.id for i in bundle.items}


def test_get_by_id_and_counts(folder):
    store = SnapshotStore.load(folder)
    assert store.get("BBB-FUND-2025-03-31").ticker == "BBB" and store.get("nope") is None
    assert store.item_count_for("aaa") == 4 and store.item_count_for("ZZZ") == 0


def test_missing_snapshot_is_a_readable_error(tmp_path):
    with pytest.raises(SnapshotError, match="missing"):
        SnapshotStore.load(tmp_path / "nope")


def test_tampered_snapshot_is_refused(folder):
    path = folder / "items.jsonl"
    path.write_bytes(path.read_bytes().replace(b"AAA closed", b"AAA CLOSED"))
    with pytest.raises(SnapshotError, match="does not match manifest"):
        SnapshotStore.load(folder)


def test_resolve_accepts_a_name_or_a_path(tmp_path):
    assert resolve_snapshot_folder("demo-v3", tmp_path) == tmp_path / "demo-v3"
    (tmp_path / "x").mkdir()
    assert resolve_snapshot_folder(tmp_path / "x", tmp_path / "elsewhere") == tmp_path / "x"


def test_empty_snapshot_works(tmp_path):
    store = SnapshotStore.load(write_snapshot([], tmp_path / "empty"))
    assert store.latest_date() is None and store.summary()["date_range"] is None and store.tickers() == []


# --- ticker names ------------------------------------------------------------------

def test_repo_ticker_file_loads_in_order():
    tickers = load_tickers()
    assert [t.ticker for t in tickers] == ["OGDC", "LUCK", "HBL", "FFC", "HUBC", "SYS"]
    assert tickers[0].company_name == "Oil & Gas Development Company Limited"


def test_ticker_file_validation(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"aaa": ["Alpha Ltd", "Old Alpha"]}), encoding="utf-8")
    t = load_tickers(path)[0]
    assert (t.ticker, t.company_name, t.names) == ("AAA", "Alpha Ltd", ("Alpha Ltd", "Old Alpha"))
    for bad in ({"AAA": []}, {"AAA": "Alpha"}, {"AAA": [""]}, ["AAA"]):
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            load_tickers(path)
    path.write_text('{"AAA": ["A"], "aaa": ["B"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_tickers(path)
