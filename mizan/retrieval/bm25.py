"""BM25 keyword search over one EvidenceBundle (the retrieval baseline).

Search runs on a bundle that build_bundle() already filtered by ticker and
as_of date, so it can never return future or other-ticker evidence.
"""

import re
from typing import Callable

from rank_bm25 import BM25Okapi

from mizan.schemas import EvidenceBundle, EvidenceItem

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be by for from has in is it its of on or that the this to was were will with".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def search(bundle: EvidenceBundle, query: str, k: int = 5,
           tokenizer: Callable[[str], list[str]] = tokenize) -> list[tuple[EvidenceItem, float]]:
    """Return up to k (item, score) pairs, best first.

    Items sharing no term with the query (score 0) are left out. Ties are
    broken by newer date first, then id, so results are deterministic.
    The same tokenizer is used for the items and the query (lexical.py supplies a normalizing one).
    """
    items = list(bundle.items)
    query_tokens = tokenizer(query)
    if not items or not query_tokens:
        return []

    bm25 = BM25Okapi([tokenizer(it.text) for it in items])
    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        (pair for pair in zip(items, scores) if pair[1] > 0),
        key=lambda pair: (-pair[1], -pair[0].date.toordinal(), pair[0].id),
    )
    return [(it, float(score)) for it, score in ranked[:k]]
