import json
from datetime import date

import pytest

from mizan.data.snapshot import write_snapshot
from mizan.retrieval.bundle import build_bundle, load_items
from mizan.schemas import EvidenceItem


def item(id, ticker, d):
    return EvidenceItem(id, ticker, "fake", "price", d, f"text {id}")


ITEMS = [
    item("BBB-1", "BBB", date(2025, 6, 2)),
    item("AAA-2", "AAA", date(2025, 6, 3)),
    item("AAA-1", "AAA", date(2025, 6, 2)),
    item("AAA-FUTURE", "AAA", date(2025, 7, 1)),
]


def test_snapshot_writes_items_and_manifest(tmp_path):
    snap = write_snapshot(ITEMS, tmp_path / "v1", meta={"note": "test"})

    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["item_count"] == 4
    assert manifest["items_by_ticker"] == {"AAA": 3, "BBB": 1}
    assert manifest["date_range"] == ["2025-06-02", "2025-07-01"]
    assert manifest["note"] == "test"
    assert len(manifest["items_sha256"]) == 64


def test_snapshot_is_sorted_and_round_trips_into_a_bundle(tmp_path):
    snap = write_snapshot(ITEMS, tmp_path / "v1")
    loaded = load_items(snap / "items.jsonl")
    assert [it.id for it in loaded] == ["AAA-1", "AAA-2", "AAA-FUTURE", "BBB-1"]

    bundle = build_bundle(loaded, "AAA", date(2025, 6, 30))
    assert [it.id for it in bundle.items] == ["AAA-1", "AAA-2"]  # future item excluded


def test_same_items_give_same_hash(tmp_path):
    a = write_snapshot(ITEMS, tmp_path / "a")
    b = write_snapshot(list(reversed(ITEMS)), tmp_path / "b")
    hash_of = lambda p: json.loads((p / "manifest.json").read_text(encoding="utf-8"))["items_sha256"]
    assert hash_of(a) == hash_of(b)


def test_refuses_to_overwrite(tmp_path):
    write_snapshot(ITEMS, tmp_path / "v1")
    with pytest.raises(FileExistsError):
        write_snapshot(ITEMS, tmp_path / "v1")


def test_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        write_snapshot(ITEMS + [ITEMS[0]], tmp_path / "v1")


def test_empty_snapshot_has_no_date_range(tmp_path):
    snap = write_snapshot([], tmp_path / "empty")
    assert json.loads((snap / "manifest.json").read_text(encoding="utf-8"))["date_range"] is None
