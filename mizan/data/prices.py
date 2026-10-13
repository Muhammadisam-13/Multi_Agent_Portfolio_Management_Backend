"""psxdata OHLCV -> EvidenceItems (one item per trading day).

fetch_prices() is the only function that touches the network; prices_to_items()
is pure so it can be tested offline.

Note: psxdata itself requests https://dps.psx.com.pk, so the same PSX Terms of
Use question applies to it as to the announcement PDFs. Keep calls few (one
request per ticker returns its whole history) and rely on the snapshot after.
"""

from datetime import date

import pandas as pd

from mizan.schemas import EvidenceItem

PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "is_anomaly"]


def fetch_prices(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch daily OHLCV from psxdata and validate it.

    Raises ValueError if the result is empty or malformed, so a silent
    upstream break does not become an empty snapshot.
    """
    import psxdata  # imported here so tests and offline code do not need it

    df = psxdata.stocks(ticker, start=start, end=end)
    return validate_prices(df, ticker, start, end)


def validate_prices(df: pd.DataFrame, ticker: str, start: date, end: date) -> pd.DataFrame:
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{ticker}: psxdata result is missing columns {missing}")
    if df.empty:
        raise ValueError(f"{ticker}: no price rows between {start} and {end}")

    df = df[PRICE_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)  # psxdata returns newest first

    if df["date"].duplicated().any():
        raise ValueError(f"{ticker}: duplicate trading dates in psxdata result")
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
