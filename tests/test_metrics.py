import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mizan.retrieval import bm25
from mizan.retrieval.bundle import load_items
from mizan.retrieval.metrics import evaluate, recall_at_k, reciprocal_rank

FIXTURES = Path(__file__).parent / "fixtures"
RESULTS = Path(__file__).parents[1] / "reports" / "bm25_gold_fixtures.json"


def test_recall_at_k():
    assert recall_at_k(["a", "b", "c"], {"a", "c"}, k=2) == 0.5
    assert recall_at_k(["a", "b", "c"], {"a", "c"}, k=3) == 1.0
    assert recall_at_k([], {"a"}, k=5) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(["x", "a"], {"a"}) == 0.5
    assert reciprocal_rank(["a"], {"a"}) == 1.0
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_gold_answer_outside_bundle_is_rejected():
    items = load_items(FIXTURES / "evidence_items.jsonl")
    gold = {"as_of": "2025-06-30", "queries": [
        {"id": "bad", "ticker": "AAA", "query": "loss", "relevant": ["AAA-ANN-2025-07-15"]},  # future item
    ]}
    with pytest.raises(ValueError, match="not in the as-of bundle"):
        evaluate(items, gold, bm25.search)


def test_bm25_on_gold_set_logs_metrics():
    """Runs BM25 on the gold set and writes the metrics to reports/.

    It logs rather than asserts a quality threshold: the numbers are for the
    report, and a low score is a finding, not a test failure.
    """
    items = load_items(FIXTURES / "evidence_items.jsonl")
    gold = json.loads((FIXTURES / "gold_queries.json").read_text(encoding="utf-8"))

    result = evaluate(items, gold, bm25.search, k=5)

    assert result["queries"] == len(gold["queries"])
    assert 0.0 <= result["recall@5"] <= 1.0 and 0.0 <= result["mrr"] <= 1.0

    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps({
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retriever": "bm25 (rank_bm25.BM25Okapi, k1=1.5, b=0.75)",
        "gold_set": "tests/fixtures/gold_queries.json (fake fixture data)",
        **result,
    }, indent=2), encoding="utf-8")
