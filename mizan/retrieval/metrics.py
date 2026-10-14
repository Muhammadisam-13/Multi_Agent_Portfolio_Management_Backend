"""Retrieval quality metrics over a hand-labelled gold set.

Gold set format (JSON):
    {"as_of": "YYYY-MM-DD",
     "queries": [{"id": ..., "ticker": ..., "query": ..., "relevant": [evidence ids]}]}
"""

from datetime import date
from typing import Callable

from mizan.retrieval.bundle import build_bundle
from mizan.schemas import EvidenceBundle, EvidenceItem

# search function: (bundle, query, k) -> ranked list of (item, score)
SearchFn = Callable[[EvidenceBundle, str, int], list[tuple[EvidenceItem, float]]]


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Share of the relevant ids found in the top k."""
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked_ids: list[str], relevant: set[str]) -> float:
    """1 / rank of the first relevant id, 0 if none was returned."""
    for rank, item_id in enumerate(ranked_ids, start=1):
        if item_id in relevant:
            return 1 / rank
    return 0.0


def evaluate(items: list[EvidenceItem], gold: dict, search: SearchFn, k: int = 5) -> dict:
    as_of = date.fromisoformat(gold["as_of"])
    per_query = []
    for q in gold["queries"]:
        relevant = set(q["relevant"])
        bundle = build_bundle(items, q["ticker"], as_of)
        missing = relevant - {it.id for it in bundle.items}
        if missing:
            # a gold answer outside the bundle (future-dated, wrong ticker, typo) is a gold-set bug
            raise ValueError(f"{q['id']}: relevant ids not in the as-of bundle: {sorted(missing)}")

        ranked = [it.id for it, _ in search(bundle, q["query"], k)]
        per_query.append({
            "id": q["id"],
            "ticker": q["ticker"],
            "query": q["query"],
            "relevant": sorted(relevant),
            "returned": ranked,
            f"recall@{k}": recall_at_k(ranked, relevant, k),
            "rr": reciprocal_rank(ranked, relevant),
        })

    n = len(per_query)
    return {
        "as_of": gold["as_of"],
        "k": k,
        "queries": n,
        f"recall@{k}": sum(r[f"recall@{k}"] for r in per_query) / n if n else 0.0,
        "mrr": sum(r["rr"] for r in per_query) / n if n else 0.0,
        "per_query": per_query,
    }
