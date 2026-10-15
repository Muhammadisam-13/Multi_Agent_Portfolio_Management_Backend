"""Build a frozen evidence snapshot from PSX financial results and (optionally) psxdata prices.

All sources run from the local cache (data/cache/) unless --live is given. With --live,
missing data is fetched once and cached; cached prices are re-fetched only with --refresh-prices.
--announcements adds PSX company announcements and their PDF text (decision D7) for --start..--end;
--reports also adds narrative chunks from the long reports (annual/quarterly) and investor presentations found among them.

Examples:
    python -m mizan.data.build_snapshot --name demo-v1 --tickers OGDC HUBC HBL --no-prices
    python -m mizan.data.build_snapshot --name demo-v2 --tickers OGDC HUBC HBL         --start 2026-04-13 --end 2026-10-12 --announcements --reports
    python -m mizan.data.build_snapshot --name demo-v1 --tickers OGDC HUBC HBL \
        --start 2026-04-13 --end 2026-10-12 --live
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from mizan.data.snapshot import write_snapshot
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import FetchError
from mizan.fetcher.results_table import FinancialResultsFetcher

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", required=True, help="snapshot folder name, e.g. demo-v1")
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--start", type=date.fromisoformat, help="first price date (needed unless --no-prices)")
    p.add_argument("--end", type=date.fromisoformat, help="last price date (needed unless --no-prices)")
    p.add_argument("--no-prices", action="store_true", help="skip the psxdata price loader")
    p.add_argument("--announcements", action="store_true", help="add PSX announcements and their PDF text (needs --start/--end)")
    p.add_argument("--reports", action="store_true", help="with --announcements: add narrative chunks of long reports")
    p.add_argument("--report-chunks", type=int, default=10, help="narrative chunks kept per report")
    p.add_argument("--live", action="store_true", help="allow network requests for missing data (default: cache only)")
    p.add_argument("--refresh-prices", action="store_true", help="re-fetch cached price histories (needs --live)")
    p.add_argument("--out-dir", type=Path, default=ROOT / "data" / "snapshots")
    args = p.parse_args(argv)
    if (not args.no_prices or args.announcements) and not (args.start and args.end):
        p.error("--start and --end are required unless --no-prices is given and --announcements is off")
    if args.reports and not args.announcements:
        p.error("--reports needs --announcements (the reports are found among the announcements)")

    tickers = [t.upper() for t in args.tickers]
    items, meta = [], {"tickers": tickers}

    config = FetchConfig(live=args.live)
    result = FinancialResultsFetcher(config).fetch(tickers)
    items += result.items
    meta["results_fetcher_notes"] = result.warnings
    for w in result.warnings:
        print(f"note: {w}")
    print(f"financial results: {len(result.items)} items")

    if args.announcements:
        from mizan.fetcher.announcements import AnnouncementsFetcher
        handler = None
        if args.reports:
            from mizan.data.reports import chunk_items, deck_items, is_periodic_report, is_presentation

            def handler(row, path):
                if is_periodic_report(row.title):
                    return chunk_items(row.symbol, row.doc_id, row.day, row.title, path, max_chunks=args.report_chunks)
                if is_presentation(row.title):
                    return deck_items(row.symbol, row.doc_id, row.day, row.title, path)
                return []
        ann = AnnouncementsFetcher(config, args.start, args.end, long_document_handler=handler).fetch(tickers)
        items += ann.items
        meta["announcements_window"] = [args.start.isoformat(), args.end.isoformat()]
        meta["announcements_notes"] = ann.warnings
        for w in ann.warnings:
            print(f"note: {w}")
        print(f"announcements: {sum(i.type == 'announcement' for i in ann.items)} items, "
              f"report chunks: {sum(i.type == 'report_section' for i in ann.items)}")

    raw_prices = {}
    if not args.no_prices:
        from mizan.data.prices import PSXDATA_VERSION, PriceLoader, prices_to_items
        loader = PriceLoader(config)
        for ticker in tickers:
            df = loader.load_prices(ticker, args.start, args.end, refresh=args.refresh_prices)
            raw_prices[ticker] = df
            items += prices_to_items(ticker, df)
            print(f"{ticker}: {len(df)} trading days {df['date'].min()}..{df['date'].max()}")
        meta["price_range"] = [args.start.isoformat(), args.end.isoformat()]
        meta["psxdata_version"] = PSXDATA_VERSION

    snap = write_snapshot(items, args.out_dir / args.name, meta=meta)
    if raw_prices:  # raw price tables next to the items so the snapshot can be audited
        (snap / "raw").mkdir()
        for ticker, df in raw_prices.items():
            df.to_csv(snap / "raw" / f"{ticker}_prices.csv", index=False)

    print(f"wrote {len(items)} items to {snap}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:   # blocked, cache miss, changed page ...: say what and stop, write nothing
        print(f"SNAPSHOT NOT WRITTEN ({type(exc).__name__}): {exc}", file=sys.stderr)
        sys.exit(1)
