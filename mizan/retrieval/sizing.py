"""How big are the bundles? (plan step 7: does a whole bundle fit in the model's context?)

Tokens are ESTIMATED from characters, because the real tokenizer (Qwen3's) is not part of this
project's dependencies: a range is reported, 4 characters per token (typical English prose) and 3
characters per token (a pessimistic figure for number-heavy text such as price rows). Exact counts can be
read from Ollama on the GPU box (`prompt_eval_count` in its response) once a bundle is formatted into a prompt.

    python -m mizan.retrieval.sizing --snapshot demo-v2 --as-of 2026-10-12
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from mizan.data.snapshot import verify_snapshot
from mizan.retrieval.bundle import build_bundle, load_items
from mizan.schemas import EvidenceItem

ROOT = Path(__file__).resolve().parents[2]
CHARS_PER_TOKEN = (4, 3)        # optimistic, pessimistic


def estimate_tokens(chars: int, chars_per_token: float) -> int:
    return math.ceil(chars / chars_per_token)


def bundle_size(items: list[EvidenceItem], ticker: str, as_of: date) -> dict:
    bundle = build_bundle(items, ticker, as_of)
    by_type: dict[str, dict] = defaultdict(lambda: {"items": 0, "chars": 0})
    for it in bundle.items:
        by_type[it.type]["items"] += 1
        by_type[it.type]["chars"] += len(it.text)
    total_chars = sum(v["chars"] for v in by_type.values())
    return {
        "ticker": ticker.upper(), "as_of": as_of.isoformat(), "items": len(bundle.items), "chars": total_chars,
        "tokens_estimate": {"4_chars_per_token": estimate_tokens(total_chars, 4),
                            "3_chars_per_token": estimate_tokens(total_chars, 3)},
        "by_type": {t: {**v, "share_of_chars": round(v["chars"] / total_chars, 3) if total_chars else 0.0}
                    for t, v in sorted(by_type.items())},
    }


def format_table(rows: list[dict], context_tokens: tuple[int, ...] = (8192, 32768)) -> str:
    types = sorted({t for r in rows for t in r["by_type"]})
    head = f"{'ticker':<7}{'items':>6}{'~tokens(4)':>11}{'~tokens(3)':>11}  " + "  ".join(f"{t[:14]:>14}" for t in types)
    out = [head, "-" * len(head)]
    for r in rows:
        cells = "  ".join(f"{r['by_type'].get(t, {}).get('items', 0):>5} ({r['by_type'].get(t, {}).get('share_of_chars', 0):>4.0%})"
                          .rjust(14) for t in types)
        out.append(f"{r['ticker']:<7}{r['items']:>6}{r['tokens_estimate']['4_chars_per_token']:>11}"
                   f"{r['tokens_estimate']['3_chars_per_token']:>11}  {cells}")
    worst = max((r["tokens_estimate"]["3_chars_per_token"] for r in rows), default=0)
    out += ["", "per-type cells: items (share of the bundle's characters); tokens are estimates, see module docstring",
            f"largest bundle, pessimistic estimate: {worst} tokens"]
    for n in context_tokens:
        out.append(f"  {'fits' if worst < n else 'DOES NOT FIT'} in a {n}-token context window "
                   f"({worst / n:.0%} used, before the question and the answer)")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--snapshot", required=True)
    p.add_argument("--as-of", dest="as_of", type=date.fromisoformat, required=True)
    p.add_argument("--tickers", nargs="*", help="default: every ticker in the snapshot")
    p.add_argument("--snapshots-dir", type=Path, default=ROOT / "data" / "snapshots")
    p.add_argument("--write-report", action="store_true", help="save reports/bundle_sizes_<snapshot>.json (counts only)")
    args = p.parse_args(argv)

    folder = Path(args.snapshot) if Path(args.snapshot).exists() else args.snapshots_dir / args.snapshot
    try:
        verify_snapshot(folder)
    except (FileNotFoundError, ValueError) as exc:
        print(f"SNAPSHOT NOT USABLE: {exc}", file=sys.stderr)
        return 1
    items = load_items(folder / "items.jsonl")
    tickers = [t.upper() for t in args.tickers] if args.tickers else sorted({i.ticker for i in items if i.ticker != "MACRO"})
    rows = [bundle_size(items, t, args.as_of) for t in tickers]
    print(f"Bundle sizes, snapshot {folder.name}, as of {args.as_of}\n")
    print(format_table(rows))

    if args.write_report:
        out = ROOT / "reports" / f"bundle_sizes_{folder.name}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({"snapshot": folder.name, "as_of": args.as_of.isoformat(),
                                   "method": "characters / 4 and / 3 (estimates, not a real tokenizer)", "bundles": rows},
                                  indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
