"""Build an as-of-dated evidence bundle for one ticker.

Hard rules enforced here (see CLAUDE.md):
  1. No look-ahead: only items with date <= as_of.
  2. Ticker isolation: only the requested ticker's items plus MACRO items.
"""

import json
from datetime import date
from pathlib import Path
from typing import Iterable

from mizan.schemas import MACRO, EvidenceBundle, EvidenceItem


def load_items(path: str | Path) -> list[EvidenceItem]:
    """Read EvidenceItems from a JSONL file (one JSON object per line)."""
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(EvidenceItem.from_dict(json.loads(line)))
    return items


def build_bundle(items: Iterable[EvidenceItem], ticker: str, as_of: date) -> EvidenceBundle:
    """Return the ticker's items and MACRO items dated on or before as_of.

    A ticker with no items of its own is not an error: the bundle then holds
    only MACRO items (or nothing). Items are sorted by (date, id) so the same
    input always gives the same bundle.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("ticker must be non-empty")
    if type(as_of) is not date:
        raise TypeError(f"as_of must be datetime.date, got {type(as_of).__name__}")

    seen_ids = set()
    selected = []
    for item in items:
        if item.id in seen_ids:
            raise ValueError(f"duplicate evidence id: {item.id}")
        seen_ids.add(item.id)
        if item.ticker in (ticker, MACRO) and item.date <= as_of:
            selected.append(item)

    selected.sort(key=lambda it: (it.date, it.id))
    return EvidenceBundle(ticker=ticker, as_of=as_of, items=tuple(selected))
