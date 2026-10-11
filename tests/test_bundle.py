from datetime import date, datetime
from pathlib import Path

import pytest

from mizan.retrieval.bundle import build_bundle, load_items
from mizan.schemas import MACRO, EvidenceItem

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_items.jsonl"
AS_OF = date(2025, 6, 30)


@pytest.fixture
def items():
    return load_items(FIXTURES)


# --- No look-ahead -------------------------------------------------------

def test_no_item_is_dated_after_as_of(items):
    for ticker in ["AAA", "BBB", "CCC"]:
        bundle = build_bundle(items, ticker, AS_OF)
        assert all(it.date <= AS_OF for it in bundle.items)


def test_future_items_exist_in_fixtures_but_are_excluded(items):
    # guard: the test is meaningless if the fixtures have no future items
    future_ids = {it.id for it in items if it.date > AS_OF}
    assert future_ids == {"AAA-ANN-2025-07-15", "MACRO-POLICY-2025-07-20"}

    bundle = build_bundle(items, "AAA", AS_OF)
    assert future_ids.isdisjoint(it.id for it in bundle.items)


def test_item_dated_exactly_as_of_is_included(items):
    bundle = build_bundle(items, "AAA", AS_OF)
    assert "AAA-ANN-2025-06-30" in {it.id for it in bundle.items}


def test_as_of_before_all_items_gives_empty_bundle(items):
    bundle = build_bundle(items, "AAA", date(2020, 1, 1))
    assert bundle.items == ()


def test_later_as_of_lets_future_items_in(items):
    bundle = build_bundle(items, "AAA", date(2025, 12, 31))
    assert "AAA-ANN-2025-07-15" in {it.id for it in bundle.items}


# --- Ticker isolation ----------------------------------------------------

def test_bundle_has_only_requested_ticker_and_macro(items):
    for ticker in ["AAA", "BBB", "CCC"]:
        bundle = build_bundle(items, ticker, AS_OF)
        assert {it.ticker for it in bundle.items} == {ticker, MACRO}


def test_bundle_has_all_eligible_items(items):
    bundle = build_bundle(items, "BBB", AS_OF)
    assert [it.id for it in bundle.items] == [
        "BBB-FUND-2025-03-31",
        "MACRO-POLICY-2025-05-05",
        "BBB-ANN-2025-05-10",
        "MACRO-CPI-2025-06-02",
        "BBB-PRICE-2025-06-27",
        "MACRO-FX-2025-06-27",
    ]


def test_ticker_is_case_insensitive(items):
    assert build_bundle(items, " aaa ", AS_OF) == build_bundle(items, "AAA", AS_OF)


# --- Empty / bad input ---------------------------------------------------

def test_unknown_ticker_returns_macro_only_without_crashing(items):
    bundle = build_bundle(items, "ZZZ", AS_OF)
    assert bundle.ticker == "ZZZ"
    assert {it.ticker for it in bundle.items} == {MACRO}


def test_no_items_at_all_returns_empty_bundle():
    bundle = build_bundle([], "AAA", AS_OF)
    assert bundle.items == ()


def test_blank_ticker_is_rejected(items):
    with pytest.raises(ValueError):
        build_bundle(items, "  ", AS_OF)


def test_datetime_as_of_is_rejected(items):
    with pytest.raises(TypeError):
        build_bundle(items, "AAA", datetime(2025, 6, 30, 16, 0))


def test_duplicate_ids_are_rejected(items):
    with pytest.raises(ValueError, match="duplicate"):
        build_bundle(items + [items[0]], "AAA", AS_OF)


# --- Schema --------------------------------------------------------------

def test_item_round_trips_through_dict(items):
    for it in items:
        assert EvidenceItem.from_dict(it.to_dict()) == it


def test_item_rejects_datetime_and_lowercase_ticker():
    with pytest.raises(TypeError):
        EvidenceItem("x", "AAA", "fake", "price", datetime(2025, 1, 1), "t")
    with pytest.raises(ValueError):
        EvidenceItem("x", "aaa", "fake", "price", date(2025, 1, 1), "t")
