"""Pick which items of a bundle go into a model's prompt when the whole bundle does not fit.

Bundles of 8k-24k tokens (docs: plan step 7) do not fit a small context window, so a bundle is cut down to a
token budget. The cut is deterministic and uses only the bundle it is given, so it cannot add look-ahead or
other tickers' items:

  1. always (while the budget lasts): the most recent price items and every financial-results item;
  2. then items ranked by BM25 relevance to the question (if there is one);
  3. then the newest remaining non-price items (announcements, report sections), newest first.
  Older daily price rows are only included when the question matches them (step 2).

Token counts are estimates (characters / chars_per_token, 3 by default = pessimistic), see sizing.py.
"""

import math
from dataclasses import dataclass, field

from mizan.retrieval import bm25
from mizan.schemas import EvidenceBundle, EvidenceItem

PER_ITEM_OVERHEAD = 12          # tokens for the id / date / source line shown with each item


def item_cost(item: EvidenceItem, chars_per_token: float) -> int:
    return math.ceil(len(item.text) / chars_per_token) + PER_ITEM_OVERHEAD


@dataclass(frozen=True)
class ContextSelection:
    items: tuple[EvidenceItem, ...]            # sorted by (date, id)
    budget_tokens: int
    used_tokens: int
    dropped: dict[str, int] = field(default_factory=dict)    # item type -> how many were left out


def select_context(bundle: EvidenceBundle, query: str | None = None, budget_tokens: int = 6000,
                   chars_per_token: float = 3.0, recent_prices: int = 3) -> ContextSelection:
    chosen: dict[str, EvidenceItem] = {}
    used = 0

    def add(item: EvidenceItem) -> None:
        nonlocal used
        cost = item_cost(item, chars_per_token)
        if item.id not in chosen and used + cost <= budget_tokens:
            chosen[item.id] = item
            used += cost

    newest_first = sorted(bundle.items, key=lambda i: (i.date, i.id), reverse=True)
    for item in [i for i in newest_first if i.type == "price"][:recent_prices]:
        add(item)
    for item in (i for i in newest_first if i.type == "financial_results"):
        add(item)

    if query:
        for item, _ in bm25.search(bundle, query, k=len(bundle.items)):
            add(item)
    for item in (i for i in newest_first if i.type != "price"):
        add(item)

    dropped: dict[str, int] = {}
    for item in bundle.items:
        if item.id not in chosen:
            dropped[item.type] = dropped.get(item.type, 0) + 1
    return ContextSelection(
        items=tuple(sorted(chosen.values(), key=lambda i: (i.date, i.id))),
        budget_tokens=budget_tokens, used_tokens=used, dropped=dict(sorted(dropped.items())))
