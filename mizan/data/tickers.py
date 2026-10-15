"""The configured tickers and their company names (data/ticker_names.json)."""

import json
from dataclasses import dataclass
from pathlib import Path

from mizan.fetcher.config import ROOT

TICKER_NAMES_PATH = ROOT / "data" / "ticker_names.json"


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    company_name: str          # the first (current) name
    names: tuple[str, ...]     # every name the company has appeared under


def load_tickers(path: str | Path = TICKER_NAMES_PATH) -> list[TickerInfo]:
    """Read {"TICKER": ["Company Name", ...]}; keeps the file's order. Raises ValueError on a malformed file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object mapping tickers to lists of names")
    tickers = []
    for ticker, names in data.items():
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            raise ValueError(f"{path}: {ticker} needs a non-empty list of company names")
        tickers.append(TickerInfo(ticker.strip().upper(), names[0], tuple(names)))
    if len({t.ticker for t in tickers}) != len(tickers):
        raise ValueError(f"{path}: duplicate tickers")
    return tickers
