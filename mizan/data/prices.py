"""psxdata OHLCV -> EvidenceItems (one item per trading day), with a local price cache.

Team decision (docs/decisions.md, 2026-10-13): live psxdata calls stay in the pipeline under
these conditions, which this module enforces:
  - live calls only when FetchConfig.live is True; tests and demos run from the cache;
  - each ticker's full history is fetched once and cached under data/cache/prices/
    (git-ignored); it is re-fetched only when refresh=True is asked for;
  - live calls are spaced by a Throttle; we add no retries on top of psxdata's own
    (up to 3 attempts, 1-2 s apart, one token refresh on 403);
  - the psxdata version is checked against PSXDATA_VERSION and every fetch is validated;
  - a refused request (PSX's X-Req-Id token, required since 2026-09-24) stops the run
    with a BlockedError that says so.

load_history() is the only function that can touch the network; validate_prices()
and prices_to_items() are pure so they can be tested offline.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from mizan.fetcher.client import Throttle
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import (
    BlockedError,
    CacheMiss,
    FetchError,
    LiveFetchDisabled,
    ServerError,
    StructureChangedError,
)
from mizan.schemas import EvidenceItem

PSXDATA_VERSION = "1.2.0"   # keep in step with requirements.txt
PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "is_anomaly"]
EARLIEST_PLAUSIBLE = date(1990, 1, 1)


@dataclass(frozen=True)
class PriceHistory:
    ticker: str
    df: pd.DataFrame          # oldest first, PRICE_COLUMNS, date as datetime.date
    fetched_utc: datetime
    from_cache: bool


# --- validation and conversion (pure) -------------------------------------------

def validate_history(df: pd.DataFrame, ticker: str, today: date | None = None) -> pd.DataFrame:
    """Check a full price history and return it sorted oldest first. Raises StructureChangedError."""
    today = today or date.today()
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        raise StructureChangedError(f"{ticker}: psxdata result is missing columns {missing}")
    if df.empty:
        raise StructureChangedError(f"{ticker}: psxdata returned no price rows (unknown or delisted ticker?)")

    df = df[PRICE_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)   # psxdata returns newest first

    if df["date"].duplicated().any():
        raise StructureChangedError(f"{ticker}: duplicate trading dates in psxdata result")
    if df["date"].min() < EARLIEST_PLAUSIBLE or df["date"].max() > today:
        raise StructureChangedError(
            f"{ticker}: implausible date range {df['date'].min()}..{df['date'].max()} (today is {today})")
    return df


def validate_prices(df: pd.DataFrame, ticker: str, start: date, end: date) -> pd.DataFrame:
    """Check a date-range slice of prices and return it sorted oldest first. Raises ValueError."""
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{ticker}: price table is missing columns {missing}")
    if df.empty:
        raise ValueError(f"{ticker}: no price rows between {start} and {end}")

    df = df[PRICE_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)

    if df["date"].duplicated().any():
        raise ValueError(f"{ticker}: duplicate trading dates")
    if df["date"].min() < start or df["date"].max() > end:
        raise ValueError(f"{ticker}: rows outside requested range {start}..{end}")
    return df


def prices_to_items(ticker: str, df: pd.DataFrame) -> list[EvidenceItem]:
    """One EvidenceItem per trading day, dated that day.

    The daily change uses the previous row's close, which is earlier data,
    so no item depends on anything after its own date.
    """
    ticker = ticker.upper()
    items = []
    prev_close = None
    for row in df.itertuples(index=False):
        change = ""
        if prev_close:
            pct = (row.close - prev_close) / prev_close * 100
            change = f", {pct:+.2f}% vs previous close {prev_close:.2f}"
        flag = " Row flagged as a data anomaly by psxdata." if row.is_anomaly else ""
        items.append(EvidenceItem(
            id=f"{ticker}-PRICE-{row.date.isoformat()}",
            ticker=ticker,
            source="psxdata",
            type="price",
            date=row.date,
            text=(f"{ticker} on {row.date.isoformat()}: open {row.open:.2f}, high {row.high:.2f}, "
                  f"low {row.low:.2f}, close {row.close:.2f} PKR{change}; "
                  f"volume {int(row.volume):,} shares.{flag}"),
        ))
        prev_close = row.close
    return items


# --- cache ----------------------------------------------------------------------

class PriceCache:
    """data/cache/prices/<TICKER>.csv plus <TICKER>.json (fetch time, version, row count, range)."""

    def __init__(self, root: Path):
        self.root = Path(root) / "prices"

    def get(self, ticker: str) -> tuple[pd.DataFrame, dict] | None:
        csv, meta = self.root / f"{ticker}.csv", self.root / f"{ticker}.json"
        if not csv.exists() or not meta.exists():
            return None
        df = pd.read_csv(csv)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df, json.loads(meta.read_text(encoding="utf-8"))

    def put(self, ticker: str, df: pd.DataFrame, meta: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.root / f"{ticker}.csv", index=False)
        (self.root / f"{ticker}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


# --- the loader -----------------------------------------------------------------

def _psxdata_history(ticker: str) -> pd.DataFrame:
    """One psxdata call for the ticker's whole history, with psxdata's errors mapped to ours."""
    import psxdata
    from psxdata.exceptions import (
        PSXAuthError, PSXConnectionError, PSXParseError, PSXRateLimitError, PSXServerError,
    )

    if psxdata.__version__ != PSXDATA_VERSION:
        raise FetchError(f"psxdata {psxdata.__version__} is installed but {PSXDATA_VERSION} is pinned; "
                         f"run pip install -r requirements.txt")
    try:
        return psxdata.stocks(ticker, cache=False)   # our cache, not psxdata's hidden one
    except PSXAuthError as exc:
        raise BlockedError(
            f"{ticker}: PSX refused the psxdata request (403). PSX requires an X-Req-Id token on data "
            f"requests since 2026-09-24 and it was not accepted. Stopping; not retrying. ({exc})") from exc
    except PSXRateLimitError as exc:
        raise BlockedError(f"{ticker}: PSX rate-limited the psxdata request (429). Stopping. ({exc})") from exc
    except (PSXConnectionError, PSXServerError) as exc:
        raise ServerError(f"{ticker}: psxdata could not reach PSX after its own retries. ({exc})") from exc
    except PSXParseError as exc:
        raise StructureChangedError(f"{ticker}: psxdata could not parse PSX's response. ({exc})") from exc


class PriceLoader:
    def __init__(self, config: FetchConfig,
                 fetch: Callable[[str], pd.DataFrame] = _psxdata_history,
                 throttle: Throttle | None = None,
                 cache: PriceCache | None = None,
                 today: Callable[[], date] = date.today):
        self.config = config
        self._fetch = fetch
        self.throttle = throttle or Throttle(config.min_interval_s)
        self.cache = cache or PriceCache(config.cache_dir)
        self._today = today

    def load_history(self, ticker: str, refresh: bool = False) -> PriceHistory:
        ticker = ticker.upper()
        cached = self.cache.get(ticker)
        if cached is not None and not refresh:
            df, meta = cached
            return PriceHistory(ticker, df, datetime.fromisoformat(meta["fetched_utc"]), from_cache=True)

        if not self.config.live:
            if refresh:
                raise LiveFetchDisabled(f"{ticker}: refresh asked for but live fetching is off")
            raise CacheMiss(f"{ticker}: no cached prices and live fetching is off (use --live once)")

        self.throttle.wait()
        df = validate_history(self._fetch(ticker), ticker, today=self._today())
        if cached is not None and len(df) < len(cached[0]):
            raise StructureChangedError(
                f"{ticker}: refreshed history has {len(df)} rows, fewer than the {len(cached[0])} cached; "
                f"keeping the cached copy")

        fetched = datetime.now(timezone.utc)
        self.cache.put(ticker, df, {
            "ticker": ticker,
            "fetched_utc": fetched.isoformat(timespec="seconds"),
            "psxdata_version": PSXDATA_VERSION,
            "rows": len(df),
            "date_range": [df["date"].min().isoformat(), df["date"].max().isoformat()],
        })
        return PriceHistory(ticker, df, fetched, from_cache=False)

    def load_prices(self, ticker: str, start: date, end: date, refresh: bool = False) -> pd.DataFrame:
        history = self.load_history(ticker, refresh=refresh)
        df = history.df
        return validate_prices(df[(df["date"] >= start) & (df["date"] <= end)], ticker.upper(), start, end)
