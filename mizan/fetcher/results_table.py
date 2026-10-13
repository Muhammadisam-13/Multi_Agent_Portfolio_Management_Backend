"""PSX financial results table -> EvidenceItems.

Source: https://www.psx.com.pk/psx/announcement/financial-announcements
A static HTML table (plain GET, no JavaScript): newest first, one date header row
per day, then one row per company filing with 9 cells. The page lists company
NAMES, not tickers, so names are mapped through data/ticker_names.json.

What this module deliberately does not do:
  - guess a ticker from a name (unknown names are counted and reported);
  - merge consolidated (CS) and unconsolidated (UCS) rows (both are kept, labelled);
  - interpret the dividend codes such as (F), (D), (i): the PSX page gives no legend,
    so the text is passed through verbatim.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from bs4 import BeautifulSoup

from mizan.fetcher.cache import PageCache, load_page
from mizan.fetcher.client import PoliteClient
from mizan.fetcher.config import ROOT, FetchConfig
from mizan.fetcher.errors import StructureChangedError
from mizan.schemas import EvidenceItem

URL = "https://www.psx.com.pk/psx/announcement/financial-announcements"
NAMESPACE = "financial_announcements"
SOURCE = "psx_financial_announcements"
TICKER_NAMES_PATH = ROOT / "data" / "ticker_names.json"

EXPECTED_HEADERS = [
    "company", "time", "year ended", "dividend", "profit / (loss) before",
    "profit / (loss) after", "eps", "annual general meeting", "closure of share transfer books",
]
PERIOD_LABELS = {  # only codes seen on the live page; anything else is passed through raw
    "YR": "year ended", "HYR": "half year ended", "IQ": "first quarter ended", "IIIQ": "third quarter ended",
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


@dataclass(frozen=True)
class ResultRow:
    company: str
    day: date          # publication date from the date header above the row
    time: str
    period: str
    dividend: str
    profit_before_tax: str
    profit_after_tax: str
    eps: str
    agm: str
    book_closure: str


@dataclass
class FetchResult:
    items: list[EvidenceItem]
    warnings: list[str]


# --- parsing ------------------------------------------------------------------

def parse_results_page(html: str, max_skipped_fraction: float = 0.05) -> tuple[list[ResultRow], list[str]]:
    """Return (rows, problems). Raises StructureChangedError if the page no longer fits."""
    soup = BeautifulSoup(html, "html.parser")
    table = next((t for t in soup.find_all("table") if _header_cells(t)[:1] == ["company"]), None)
    if table is None:
        raise StructureChangedError("no results table (first header cell 'Company') found")

    headers = _header_cells(table)
    if len(headers) != len(EXPECTED_HEADERS) or any(
            not h.startswith(e) for h, e in zip(headers, EXPECTED_HEADERS)):
        raise StructureChangedError(f"results table columns changed: {headers}")

    rows, problems, current_day = [], [], None
    for tr in table.find_all("tr"):
        h4 = tr.find("h4")
        if h4 is not None:
            text = h4.get_text(strip=True)
            try:
                current_day = datetime.strptime(text, "%b %d, %Y").date()
            except ValueError:
                raise StructureChangedError(f"unreadable date header: {text!r}")
            continue
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
        if not cells or cells[0].lower() == "company":
            continue
        if len(cells) != 9 or current_day is None:
            problems.append(f"skipped row ({len(cells)} cells, date header {'seen' if current_day else 'missing'}): "
                            f"{' | '.join(cells)[:100]}")
            continue
        rows.append(ResultRow(cells[0], current_day, *cells[1:]))

    if not rows:
        raise StructureChangedError("results table has no data rows")
    if len(problems) / (len(rows) + len(problems)) > max_skipped_fraction:
        raise StructureChangedError(f"{len(problems)} of {len(rows) + len(problems)} rows unreadable")
    return rows, problems


def _header_cells(table) -> list[str]:
    first = table.find("tr")
    if first is None:
        return []
    return [" ".join(c.get_text(" ", strip=True).lower().split()) for c in first.find_all(["td", "th"])]


# --- ticker names -------------------------------------------------------------

def normalize_name(name: str) -> str:
    return " ".join(name.casefold().split())


def load_name_map(path: Path = TICKER_NAMES_PATH) -> dict[str, str]:
    """{normalized company name: TICKER} from a file shaped {"TICKER": ["Company Name", ...]}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for ticker, names in data.items():
        for name in names:
            key = normalize_name(name)
            if mapping.get(key, ticker) != ticker:
                raise ValueError(f"company name {name!r} is mapped to both {mapping[key]} and {ticker}")
            mapping[key] = ticker.upper()
    return mapping


# --- rows -> evidence ---------------------------------------------------------

def rows_to_items(rows: Sequence[ResultRow], name_map: dict[str, str],
                  tickers: Sequence[str] | None = None) -> tuple[list[EvidenceItem], Counter]:
    """Evidence items for mapped companies, plus a count of company names that had no ticker.

    If tickers is given, only those tickers are kept (other mapped companies are dropped silently).
    """
    wanted = {t.upper() for t in tickers} if tickers else None
    unmatched: Counter = Counter()
    items = []
    for row in rows:
        ticker = name_map.get(normalize_name(row.company))
        if ticker is None:
            unmatched[row.company] += 1
            continue
        if wanted is not None and ticker not in wanted:
            continue
        items.append(_row_to_item(row, ticker))
    _check_unique(items)
    return items, unmatched


def _row_to_item(row: ResultRow, ticker: str) -> EvidenceItem:
    clock = row.time.replace(":", "")
    period = _parse_period(row.period)
    basis = _basis(row)
    announced = f"{ticker} announced on {row.day.isoformat()} at {row.time}"
    has_figures = any(v != "-" for v in (row.profit_before_tax, row.profit_after_tax, row.eps))

    if period is None and not has_figures:
        kind, id_tail = "corporate_notice", f"NOTICE-{row.day.isoformat()}-{clock}"
        text = f"{announced} a corporate notice with no financial figures."
    else:
        kind = "financial_results"
        code = f"{period[0].strftime('%Y%m%d')}{period[1]}" if period else "NOPERIOD"
        id_tail = f"RESULT-{row.day.isoformat()}-{code}-{basis.upper()}-{clock}"
        label = _period_label(row.period, period)
        text = f"{announced} its financial results for the {label} ({basis}):"
        parts = []
        if row.profit_before_tax != "-":
            parts.append(f"profit before taxation {_money(row.profit_before_tax)}")
        if row.profit_after_tax != "-":
            parts.append(f"profit after taxation {_money(row.profit_after_tax)}")
        if row.eps != "-":
            parts.append(f"earnings per share {_per_share(row.eps)}")
        text += " " + (", ".join(parts) if parts else "no profit figures given") + "."

    if row.dividend != "-":
        text += f" Dividend/bonus/right as announced: {row.dividend}."
    if row.agm != "-":
        text += f" Annual/extraordinary general meeting: {row.agm}."
    if row.book_closure != "-":
        text += f" Share transfer books closed: {row.book_closure}."

    return EvidenceItem(id=f"{ticker}-{id_tail}", ticker=ticker, source=SOURCE,
                        type=kind, date=row.day, text=text)


def _parse_period(raw: str) -> tuple[date, str] | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})\((YR|HYR|IQ|IIIQ)\)", raw.strip())
    if not m:
        return None
    try:
        return date(int(m[3]), int(m[2]), int(m[1])), m[4]
    except ValueError:
        return None


def _period_label(raw: str, period: tuple[date, str] | None) -> str:
    if period is None:
        return f"period '{raw}'"
    end, code = period
    return f"{PERIOD_LABELS[code]} {end.day} {MONTHS[end.month - 1]} {end.year}"


def _basis(row: ResultRow) -> str:
    for value in (row.profit_after_tax, row.profit_before_tax):
        m = re.search(r"\((UCS|CS)\)", value)
        if m:
            return "consolidated" if m[1] == "CS" else "unconsolidated"
    return "unspecified"


def _clean(value: str) -> str:
    return re.sub(r"\s*\((?:UCS|CS)\)\s*$", "", value).strip()


def _money(value: str) -> str:
    v = _clean(value)
    if v.startswith("(") and v.endswith(")"):       # header says Profit / (Loss): parentheses = loss
        return f"(loss) of Rs {v[1:-1]} million"
    return f"Rs {v} million"


def _per_share(value: str) -> str:
    v = _clean(value)
    if v.startswith("(") and v.endswith(")"):
        return f"(loss per share) of Rs {v[1:-1]}"
    return f"Rs {v}"


def _check_unique(items: list[EvidenceItem]) -> None:
    ids = Counter(it.id for it in items)
    dupes = [i for i, n in ids.items() if n > 1]
    if dupes:
        raise StructureChangedError(f"duplicate evidence ids from the results table: {dupes[:3]}")


# --- the fetcher --------------------------------------------------------------

class FinancialResultsFetcher:
    """Evidence from PSX's financial results table (swappable: any object with fetch(tickers))."""

    name = "psx_financial_results"

    def __init__(self, config: FetchConfig, name_map: dict[str, str] | None = None,
                 client: PoliteClient | None = None, cache: PageCache | None = None):
        self.config = config
        self.name_map = name_map if name_map is not None else load_name_map()
        self.client = client or PoliteClient(config)
        self.cache = cache or PageCache(config.cache_dir)

    def fetch(self, tickers: Sequence[str]) -> FetchResult:
        page, warning = load_page(NAMESPACE, URL, self.config, self.client, self.cache,
                                  validate=parse_results_page)
        rows, problems = parse_results_page(page.text)
        items, unmatched = rows_to_items(rows, self.name_map, tickers)

        warnings = [warning] if warning else []
        warnings += problems
        warnings.append(f"results table page fetched {page.fetched_utc.isoformat()}, "
                        f"{len(rows)} rows from {min(r.day for r in rows)} to {max(r.day for r in rows)}")
        found = {it.ticker for it in items}
        for t in sorted({t.upper() for t in tickers} - found):
            warnings.append(f"no results rows for {t} in this page window "
                            f"(not reported recently, or its company name is missing from ticker_names.json)")
        return FetchResult(items=items, warnings=warnings)
