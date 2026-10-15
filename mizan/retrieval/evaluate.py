"""Evaluate BM25 on a snapshot against a hand-labelled gold file (recall@k, MRR).

    python -m mizan.retrieval.evaluate --snapshot demo-v2 --gold eval/gold_demo-v2.json --write-report

Gold file format (same as tests/fixtures/gold_queries.json):
    {"as_of": "YYYY-MM-DD", "queries": [{"id", "ticker", "query", "relevant": [evidence ids]}]}
A gold answer that is not in the as-of bundle (future-dated, wrong ticker, mistyped id) is an error.
The report is rewritten only when the scores change, so reruns leave git clean.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mizan.data.snapshot import verify_snapshot
from mizan.retrieval import bm25, lexical
from mizan.retrieval.bundle import load_items
from mizan.retrieval.metrics import evaluate

ROOT = Path(__file__).resolve().parents[2]
RETRIEVERS = {"bm25": bm25.search, "bm25-norm": lexical.search_normalized}


def write_report_if_changed(path: Path, report: dict) -> bool:
    """Write the report with a timestamp unless the saved one has identical scores. Returns True if written."""
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if {k: v for k, v in old.items() if k != "run_utc"} == report:
            return False
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **report},
                               indent=2), encoding="utf-8")
    return True


def by_difficulty(result: dict, gold: dict, k: int) -> dict:
    """Mean recall@k and MRR per 'difficulty' label in the gold file (queries without a label are skipped)."""
    labels = {q["id"]: q["difficulty"] for q in gold["queries"] if "difficulty" in q}
    groups: dict[str, list[dict]] = {}
    for q in result["per_query"]:
        if q["id"] in labels:
            groups.setdefault(labels[q["id"]], []).append(q)
    return {label: {"queries": len(qs), f"recall@{k}": sum(q[f"recall@{k}"] for q in qs) / len(qs),
                    "mrr": sum(q["rr"] for q in qs) / len(qs)}
            for label, qs in sorted(groups.items())}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", required=True)
    p.add_argument("--gold", type=Path, required=True)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--retriever", choices=sorted(RETRIEVERS), default="bm25", help="bm25 (plain) or bm25-norm (stemming + abbreviations)")
    p.add_argument("--snapshots-dir", type=Path, default=ROOT / "data" / "snapshots")
    p.add_argument("--write-report", action="store_true", help="save reports/<retriever>_<gold file>_<snapshot>.json")
    args = p.parse_args(argv)

    folder = Path(args.snapshot) if Path(args.snapshot).exists() else args.snapshots_dir / args.snapshot
    try:
        verify_snapshot(folder)
        gold = json.loads(args.gold.read_text(encoding="utf-8"))
        result = evaluate(load_items(folder / "items.jsonl"), gold, RETRIEVERS[args.retriever], k=args.k)
    except (FileNotFoundError, ValueError) as exc:
        print(f"EVALUATION NOT RUN: {exc}", file=sys.stderr)
        return 1

    key = f"recall@{args.k}"
    result["by_difficulty"] = by_difficulty(result, gold, args.k)
    print(f"{args.retriever} on snapshot {folder.name}, gold {args.gold.name}, {result['queries']} queries, as of {result['as_of']}")
    print(f"  {key} = {result[key]:.2f}   MRR = {result['mrr']:.2f}")
    for label, g in result["by_difficulty"].items():
        print(f"    {label:<7} {g['queries']:>2} queries   {key} = {g[key]:.2f}   MRR = {g['mrr']:.2f}")
    print()
    for q in result["per_query"]:
        mark ="ok  " if q["rr"] == 1.0 else ("part" if q["rr"] > 0 else "MISS")
        print(f"  {mark} {q['id']} [{q['ticker']}] {q['query']!r}: first hit rank "
              f"{round(1 / q['rr']) if q['rr'] else '-'}; returned {len(q['returned'])}")
        if q["rr"] < 1.0:
            print(f"        wanted   {q['relevant']}\n        returned {q['returned'][:3]}")

    if args.write_report:
        report = {"retriever": f"{args.retriever} (rank_bm25.BM25Okapi, k1=1.5, b=0.75)", "snapshot": folder.name,
                  "gold_set": args.gold.name, **result}
        out = ROOT / "reports" / f"{args.retriever}_{args.gold.stem}_{folder.name}.json"
        print(f"\n{'wrote' if write_report_if_changed(out, report) else 'unchanged:'} {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
