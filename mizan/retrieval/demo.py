"""Build and print an as-of bundle from a snapshot, showing what the two hard rules left out.

    python -m mizan.retrieval.demo --snapshot demo-v1 --ticker OGDC --as-of 2026-09-08
    python -m mizan.retrieval.demo --snapshot demo-v1 --ticker OGDC --as-of 2026-09-08 --compare-as-of 2026-09-01
    python -m mizan.retrieval.demo --snapshot demo-v1 --ticker OGDC --as-of 2026-09-08 --query "dividend payout"

It runs from the local snapshot only (no network). The snapshot is checked against its committed
manifest first; a mismatch stops the run.
"""

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from mizan.data.snapshot import verify_snapshot
from mizan.retrieval import bm25, lexical
from mizan.retrieval.bundle import build_bundle, load_items
from mizan.retrieval.context import select_context
from mizan.schemas import EvidenceItem

ROOT = Path(__file__).resolve().parents[2]


def _preview(text: str, width: int = 170) -> str:
    return text if len(text) <= width else text[:width].rstrip() + "..."


def _counts(items) -> str:
    counts = Counter(i.type for i in items)
    return ", ".join(f"{n} {t}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])) or "none"


def build_report(items: list[EvidenceItem], ticker: str, as_of: date, snapshot_label: str = "snapshot",
                 limit: int = 12, price_rows: int = 2, query: str | None = None, k: int = 5,
                 compare_as_of: date | None = None, budget_tokens: int | None = None, search_fn=lexical.search_normalized) -> str:
    ticker = ticker.upper()
    bundle = build_bundle(items, ticker, as_of)
    mine = [i for i in items if i.ticker == ticker]
    future = sorted((i for i in mine if i.date > as_of), key=lambda i: (i.date, i.id))
    others = [i for i in items if i.ticker not in (ticker, "MACRO")]

    out = [f"Bundle for {ticker} as of {as_of}  ({snapshot_label})",
           f"  {len(bundle.items)} items: {_counts(bundle.items)}"]
    if bundle.items:
        out.append(f"  dated {bundle.items[0].date} to {bundle.items[-1].date}; "
                   f"tickers in the bundle: {sorted({i.ticker for i in bundle.items})}")
    if not mine:
        out.append(f"  no data for {ticker} in this snapshot (tickers present: "
                   f"{sorted({i.ticker for i in items if i.ticker != 'MACRO'})}); "
                   f"the bundle holds only MACRO items or nothing, not an error")

    out += ["", "Rule 1, no look-ahead:",
            f"  {len(future)} {ticker} items dated after {as_of} were left out"
            + (f" (earliest: {future[0].date}  {future[0].id})" if future else "")]
    out += ["Rule 2, ticker isolation:",
            f"  {len(others)} items belonging to other tickers were left out; MACRO items included: "
            f"{sum(i.ticker == 'MACRO' for i in bundle.items)}"]

    non_price = [i for i in reversed(bundle.items) if i.type != "price"]
    out += ["", f"Newest {min(limit, len(non_price))} of {len(non_price)} non-price items:"]
    for i in non_price[:limit]:
        out += [f"  {i.date}  {i.type:<17} {i.source:<28} {i.id}", f"      {_preview(i.text)}"]
    prices = [i for i in reversed(bundle.items) if i.type == "price"]
    out += ["", f"Price items: {len(prices)} (latest {min(price_rows, len(prices))} shown)"]
    for i in prices[:price_rows]:
        out += [f"  {i.date}  {i.id}", f"      {_preview(i.text)}"]

    if compare_as_of is not None:
        other = {i.id for i in build_bundle(items, ticker, compare_as_of).items}
        now = {i.id for i in bundle.items}
        label = "added" if compare_as_of < as_of else "removed"
        diff = sorted((i for i in bundle.items + build_bundle(items, ticker, compare_as_of).items
                       if (i.id in now) != (i.id in other)), key=lambda i: (i.date, i.id))
        diff = list({i.id: i for i in diff}.values())
        out += ["", f"Compared with as of {compare_as_of}: {len(diff)} items {label} "
                    f"({len(other)} -> {len(now)} items)"]
        for i in [d for d in diff if d.type != "price"][:limit]:
            out += [f"  {i.date}  {i.type:<17} {i.id}", f"      {_preview(i.text)}"]
        out.append(f"  (+ {sum(d.type == 'price' for d in diff)} price items)")

    if query:
        out += ["", f"BM25 search in this bundle for {query!r} (top {k}):"]
        hits = search_fn(bundle, query, k)
        for rank, (i, score) in enumerate(hits, 1):
            out += [f"  {rank}. score {score:.2f}  {i.date}  {i.id}", f"      {_preview(i.text)}"]
        if not hits:
            out.append("  no item shares a word with the query")
    if budget_tokens is not None:
        sel = select_context(bundle, query, budget_tokens, search_fn=search_fn)
        out += ["", f"Context for the model: budget {budget_tokens} tokens (estimate), used {sel.used_tokens}, "
                    f"{len(sel.items)} of {len(bundle.items)} items" + (f", question {query!r}" if query else ", no question"),
                f"  left out: {', '.join(f'{n} {t}' for t, n in sel.dropped.items()) or 'nothing'}"]
        for i in sel.items:
            if i.type != "price":
                out.append(f"  {i.date}  {i.type:<17} {i.id}")
        out.append(f"  (+ {sum(i.type == 'price' for i in sel.items)} price items)")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", required=True, help="snapshot name under data/snapshots/ (or a path)")
    p.add_argument("--ticker", required=True)
    p.add_argument("--as-of", dest="as_of", type=date.fromisoformat, required=True)
    p.add_argument("--compare-as-of", dest="compare_as_of", type=date.fromisoformat)
    p.add_argument("--query")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--retriever", choices=["bm25-norm", "bm25"], default="bm25-norm", help="search used for --query and --budget")
    p.add_argument("--budget", type=int, help="also show the items a model with this many tokens of room would get")
    p.add_argument("--limit", type=int, default=12, help="non-price items to show")
    p.add_argument("--snapshots-dir", type=Path, default=ROOT / "data" / "snapshots")
    args = p.parse_args(argv)

    folder = Path(args.snapshot)
    if not folder.exists():
        folder = args.snapshots_dir / args.snapshot
    try:
        verify_snapshot(folder)
    except (FileNotFoundError, ValueError) as exc:
        print(f"SNAPSHOT NOT USABLE: {exc}", file=sys.stderr)
        return 1

    items = load_items(folder / "items.jsonl")
    print(build_report(items, args.ticker, args.as_of, f"snapshot {folder.name}, verified against its manifest",
                       limit=args.limit, query=args.query, k=args.k, compare_as_of=args.compare_as_of,
                       budget_tokens=args.budget,
                       search_fn=lexical.search_normalized if args.retriever == "bm25-norm" else bm25.search))
    return 0


if __name__ == "__main__":
    sys.exit(main())
