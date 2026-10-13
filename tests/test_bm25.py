from datetime import date
from pathlib import Path

import pytest

from mizan.retrieval.bm25 import search, tokenize
from mizan.retrieval.bundle import build_bundle, load_items

FIXTURES = Path(__file__).parent / "fixtures" / "evidence_items.jsonl"
AS_OF = date(2025, 6, 30)


@pytest.fixture
def items():
    return load_items(FIXTURES)


def ids(results):
    return [it.id for it, _ in results]


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("The Board approved a DIVIDEND of 3.00") == ["board", "approved", "dividend", "3", "00"]


def test_relevant_item_ranks_first(items):
    bundle = build_bundle(items, "AAA", AS_OF)
    assert ids(search(bundle, "dividend"))[0] == "AAA-ANN-2025-04-25"
    assert ids(search(bundle, "policy rate cut"))[0] == "MACRO-POLICY-2025-05-05"


def test_search_never_returns_future_or_other_ticker_items(items):
    bundle = build_bundle(items, "AAA", AS_OF)
    # these words appear only in excluded items (AAA future loss, BBB expansion)
    results = search(bundle, "one-off loss expansion delayed raised", k=50)
    for it, _ in results:
        assert it.date <= AS_OF
        assert it.ticker in {"AAA", "MACRO"}


def test_scores_are_descending_and_k_is_respected(items):
    bundle = build_bundle(items, "AAA", AS_OF)
    results = search(bundle, "closed day volume shares PKR", k=2)
    assert len(results) == 2
    assert results[0][1] >= results[1][1]


def test_no_matching_terms_returns_empty(items):
    bundle = build_bundle(items, "AAA", AS_OF)
    assert search(bundle, "cryptocurrency") == []


@pytest.mark.parametrize("query", ["", "   ", "the of and"])
def test_empty_or_stopword_query_returns_empty(items, query):
    assert search(build_bundle(items, "AAA", AS_OF), query) == []


def test_empty_bundle_returns_empty():
    assert search(build_bundle([], "AAA", AS_OF), "dividend") == []
