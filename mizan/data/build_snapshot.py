"""Build a frozen evidence snapshot from psxdata prices.

Announcements from mizan.fetcher are added here once the fetcher exists (plan step 9).

Example:
    python -m mizan.data.build_snapshot --name demo-v1 --tickers OGDC HBL \
        --start 2025-06-01 --end 2025-06-30
"""

import argparse
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

from mizan.data.prices import fetch_prices, prices_to_items
from mizan.data.snapshot import write_snapshot

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", required=True, help="snapshot folder name, e.g. demo-v1")
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--out-dir", type=Path, default=ROOT / "data" / "snapshots")
    args = p.parse_args(argv)

    items = []
    raw_prices = {}
    for ticker in args.tickers:
        df = fetch_prices(ticker.upper(), args.start, args.end)
        raw_prices[ticker.upper()] = df
        items += prices_to_items(ticker, df)
        print(f"{ticker.upper()}: {len(df)} trading days {df['date'].min()}..{df['date'].max()}")

    snap = write_snapshot(items, args.out_dir / args.name, meta={
        "tickers": [t.upper() for t in args.tickers],
        "price_range": [args.start.isoformat(), args.end.isoformat()],
        "psxdata_version": version("psxdata"),
    })
    # keep the raw price tables next to the items so the snapshot can be audited
    (snap / "raw").mkdir()
    for ticker, df in raw_prices.items():
        df.to_csv(snap / "raw" / f"{ticker}_prices.csv", index=False)

    print(f"wrote {len(items)} items to {snap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
