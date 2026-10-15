"""Run a fetcher by hand and print what it returns.

    python -m mizan.fetcher.cli --tickers OGDC HUBC HBL                        # financial results, cache only
    python -m mizan.fetcher.cli --tickers OGDC --live                          # may fetch one page from PSX
    python -m mizan.fetcher.cli --source announcements --tickers OGDC \\
        --from 2026-04-13 --to 2026-10-12 --live --interval 4                  # announcements + their PDFs (D7)
"""

import argparse
import sys
from datetime import date

from mizan.fetcher.announcements import AnnouncementsFetcher
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import FetchError
from mizan.fetcher.results_table import FinancialResultsFetcher


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", choices=["results", "announcements"], default="results")
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--from", dest="date_from", type=date.fromisoformat, help="announcements: first date (YYYY-MM-DD)")
    p.add_argument("--to", dest="date_to", type=date.fromisoformat, help="announcements: last date (YYYY-MM-DD)")
    p.add_argument("--live", action="store_true", help="allow network requests (default: cache only)")
    p.add_argument("--interval", type=float, default=5.0, help="seconds between requests")
    p.add_argument("--show", type=int, default=5, help="print this many items per ticker")
    args = p.parse_args(argv)

    config = FetchConfig(live=args.live, min_interval_s=args.interval)
    if args.source == "announcements":
        if not (args.date_from and args.date_to):
            p.error("--from and --to are required for --source announcements")
        fetcher = AnnouncementsFetcher(config, args.date_from, args.date_to)
    else:
        fetcher = FinancialResultsFetcher(config)

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
            print(f"  {item.id}\n    {item.text[:400]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
