"""Run the results-table fetcher by hand.

    python -m mizan.fetcher.cli --tickers OGDC HUBC HBL            # from cache only
    python -m mizan.fetcher.cli --tickers OGDC HUBC HBL --live     # may fetch one page from PSX
"""

import argparse
import sys

from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import FetchError
from mizan.fetcher.results_table import FinancialResultsFetcher


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--live", action="store_true", help="allow network requests (default: cache only)")
    p.add_argument("--interval", type=float, default=5.0, help="seconds between requests")
    p.add_argument("--show", type=int, default=5, help="print this many items per ticker")
    args = p.parse_args(argv)

    fetcher = FinancialResultsFetcher(FetchConfig(live=args.live, min_interval_s=args.interval))
    try:
        result = fetcher.fetch(args.tickers)
    except FetchError as exc:
        print(f"FETCH FAILED ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1

    for w in result.warnings:
        print(f"note: {w}")
    for ticker in sorted({t.upper() for t in args.tickers}):
        mine = sorted((i for i in result.items if i.ticker == ticker), key=lambda i: (i.date, i.id), reverse=True)
        print(f"\n{ticker}: {len(mine)} items")
        for item in mine[:args.show]:
            print(f"  {item.id}\n    {item.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
