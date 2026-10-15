"""PSX company announcements (dps.psx.com.pk) -> EvidenceItems. Decision D7, docs/decisions.md.

The announcements page loads its list with `POST /announcements` and returns an HTML fragment:
a header ("Showing 1 to 50 of 731 entries", with data-total), then `table#announcementsTable`
with rows DATE | TIME | SYMBOL | NAME | TITLE | links. Each row links the filing as
`/download/document/<id>.pdf`. The list is read through DpsSession (the page's own token);
the short PDFs are downloaded once and cached, and their text becomes the body of the item.

Choices worth knowing:
  - the item id is the PSX document id (`OGDC-ANN-282420`): stable and unique;
  - the item date is the announcement date shown by PSX (time of day is kept in the text only);
  - a PDF with no text layer is flagged (needs OCR), not turned into an empty body;
  - documents longer than max_pdf_pages (annual reports) are not inlined: the item keeps the
    title and says so, the report pipeline handles those;
  - PDFs are cached under data/cache/ (git-ignored) and never committed.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from bs4 import BeautifulSoup

from mizan.data.pdf_extract import extract_text
from mizan.fetcher.base import FetchResult
from mizan.fetcher.cache import PageCache, load_cached
from mizan.fetcher.client import PoliteClient
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.dps_session import BASE, TOKEN_PAGE, DpsSession
from mizan.fetcher.errors import BlockedError, FetchError, StructureChangedError
from mizan.schemas import EvidenceItem

SOURCE = "psx_announcements"
EXPECTED_HEADERS = ["DATE", "TIME", "SYMBOL", "NAME", "TITLE"]
DOC_LINK = re.compile(r"/download/document/(\d+)\.pdf")


@dataclass(frozen=True)
class AnnouncementRow:
    day: date
    time: str
    symbol: str
    name: str
    title: str
    doc_id: str | None


@dataclass(frozen=True)
class DocText:
    status: str            # text | needs_ocr | long | not_cached | download_failed | unreadable | no_document
    text: str = ""
    pages: int = 0


# --- parsing ------------------------------------------------------------------

def parse_announcements_page(html: str, max_skipped_fraction: float = 0.05
                             ) -> tuple[list[AnnouncementRow], int, list[str]]:
    """Return (rows, total entries on the server for this query, problems)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="announcementsTable")
    if table is None:
        raise StructureChangedError("announcements table (#announcementsTable) not found")
    headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]
    if headers[:5] != EXPECTED_HEADERS:
        raise StructureChangedError(f"announcements table columns changed: {headers}")
    counter = soup.find(attrs={"data-total": True})
    if counter is None:
        raise StructureChangedError("announcements paging counter (data-total) not found")
    total = int(counter["data-total"])

    rows, problems = [], []
    body = table.find("tbody")
    for tr in (body.find_all("tr") if body else []):
        cells = tr.find_all("td")
        text = [" ".join(c.get_text(" ", strip=True).split()) for c in cells]
        try:
            if len(cells) != 6:
                raise ValueError(f"{len(cells)} cells")
            day = datetime.strptime(text[0], "%b %d, %Y").date()
        except ValueError as exc:
            problems.append(f"skipped announcement row ({exc}): {' | '.join(text)[:100]}")
            continue
        link = DOC_LINK.search(str(cells[5]))
        rows.append(AnnouncementRow(day, text[1], text[2].upper(), text[3], text[4], link.group(1) if link else None))

    if problems and len(problems) / (len(rows) + len(problems)) > max_skipped_fraction:
        raise StructureChangedError(f"{len(problems)} of {len(rows) + len(problems)} announcement rows unreadable")
    return rows, total, problems


# --- documents ------------------------------------------------------------------

class PdfCache:
    """data/cache/announcement_pdfs/<document id>.pdf, downloaded once and never overwritten."""

    def __init__(self, root: Path):
        self.root = Path(root) / "announcement_pdfs"

    def path(self, doc_id: str) -> Path:
        if not doc_id.isdigit():
            raise ValueError(f"unexpected document id {doc_id!r}")
        return self.root / f"{doc_id}.pdf"

    def has(self, doc_id: str) -> bool:
        return self.path(doc_id).exists()

    def put(self, doc_id: str, content: bytes) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(doc_id)
        path.write_bytes(content)
        return path


def describe_document(path: Path, max_pdf_pages: int, max_text_chars: int) -> DocText:
    try:
        extracted = extract_text(path)
    except Exception:
        return DocText("unreadable")
    if extracted.pages > max_pdf_pages:
        return DocText("long", pages=extracted.pages)
    if extracted.needs_ocr:
        return DocText("needs_ocr", pages=extracted.pages)
    text = " ".join(extracted.text.split())
    if len(text) > max_text_chars:
        text = text[:max_text_chars].rstrip() + " [truncated]"
    return DocText("text", text, extracted.pages)


# --- rows -> evidence -----------------------------------------------------------

DOC_NOTES = {
    "needs_ocr": "The attached PDF has no text layer, so its content is not available (needs OCR).",
    "not_cached": "The attached PDF was not downloaded.",
    "download_failed": "The attached PDF could not be downloaded.",
    "unreadable": "The attached PDF could not be read.",
    "no_document": "PSX lists no document for this announcement.",
}


def row_to_item(row: AnnouncementRow, doc: DocText) -> EvidenceItem:
    ticker = row.symbol
    if row.doc_id:
        item_id = f"{ticker}-ANN-{row.doc_id}"
    else:
        digest = hashlib.sha1(f"{row.day}|{row.time}|{row.title}".encode("utf-8")).hexdigest()[:8]
        item_id = f"{ticker}-ANN-{row.day.strftime('%Y%m%d')}-{digest}"

    text = f"{ticker} announcement on {row.day.isoformat()} at {row.time}: {row.title.rstrip('. ')}."
    if doc.status == "text":
        text += f" Document text: {doc.text}"
    elif doc.status == "long":
        text += f" The attached document is {doc.pages} pages long and is not included here."
    else:
        text += " " + DOC_NOTES[doc.status]
    return EvidenceItem(id=item_id, ticker=ticker, source=SOURCE, type="announcement", date=row.day, text=text)


# --- the fetcher ----------------------------------------------------------------

class AnnouncementsFetcher:
    """Company announcements for tickers in [date_from, date_to] (swappable: fetch(tickers) -> FetchResult)."""

    name = "psx_announcements"

    def __init__(self, config: FetchConfig, date_from: date, date_to: date,
                 client: PoliteClient | None = None, session: DpsSession | None = None,
                 cache: PageCache | None = None, pdf_cache: PdfCache | None = None,
                 page_size: int = 50, max_pages: int = 6, max_pdf_pages: int = 8, max_text_chars: int = 4000):
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        self.config, self.date_from, self.date_to = config, date_from, date_to
        self.client = client or PoliteClient(config)
        self.session = session or DpsSession(self.client)
        self.cache = cache or PageCache(config.cache_dir)
        self.pdf_cache = pdf_cache or PdfCache(config.cache_dir)
        self.page_size, self.max_pages = page_size, max_pages
        self.max_pdf_pages, self.max_text_chars = max_pdf_pages, max_text_chars

    def fetch(self, tickers: Sequence[str]) -> FetchResult:
        items: list[EvidenceItem] = []
        warnings: list[str] = []
        for ticker in dict.fromkeys(t.upper() for t in tickers):
            rows = self._list_rows(ticker, warnings)
            statuses = {}
            seen: set[str] = set()
            for row in rows:
                key = row.doc_id or f"{row.day}|{row.time}|{row.title}"
                if key in seen:
                    continue
                seen.add(key)
                doc = self._document(row, warnings)
                statuses[doc.status] = statuses.get(doc.status, 0) + 1
                items.append(row_to_item(row, doc))
            if not rows:
                warnings.append(f"{ticker}: no announcements between {self.date_from} and {self.date_to}")
            else:
                warnings.append(f"{ticker}: {len(seen)} announcements ({', '.join(f'{n} {s}' for s, n in sorted(statuses.items()))})")
        return FetchResult(items=items, warnings=warnings)

    def _list_rows(self, ticker: str, warnings: list[str]) -> list[AnnouncementRow]:
        rows: list[AnnouncementRow] = []
        offset = 0
        for page_no in range(self.max_pages):
            payload = {"type": "C", "symbol": ticker, "query": "", "count": self.page_size, "offset": offset,
                       "date_from": self.date_from.isoformat(), "date_to": self.date_to.isoformat(), "page": "annc"}
            namespace = f"announcements/{ticker}_{self.date_from}_{self.date_to}_{offset}"
            page, warning = load_cached(
                namespace, f"POST {BASE}/announcements", self.config, self.cache,
                fetch=lambda p=payload: self.session.post_form("/announcements", p),
                validate=parse_announcements_page)
            if warning:
                warnings.append(warning)
            parsed, total, problems = parse_announcements_page(page.text)
            warnings += problems
            rows += parsed
            offset += self.page_size
            if offset >= total or not parsed:
                break
        else:
            warnings.append(f"{ticker}: stopped after {self.max_pages} pages ({len(rows)} rows); more exist on PSX")

        kept = []
        for r in rows:
            if r.symbol != ticker:
                warnings.append(f"{ticker}: dropped a row for {r.symbol} ({r.title[:40]!r})")
            elif not self.date_from <= r.day <= self.date_to:
                warnings.append(f"{ticker}: dropped a row dated {r.day} outside the requested window")
            else:
                kept.append(r)
        return kept

    def _document(self, row: AnnouncementRow, warnings: list[str]) -> DocText:
        if not row.doc_id:
            return DocText("no_document")
        if not self.pdf_cache.has(row.doc_id):
            if not self.config.live:
                return DocText("not_cached")
            try:
                content = self.client.get_bytes(f"{BASE}/download/document/{row.doc_id}.pdf",
                                                headers={"Referer": TOKEN_PAGE})
            except BlockedError:
                raise
            except FetchError as exc:
                warnings.append(f"document {row.doc_id}: {type(exc).__name__}: {exc}")
                return DocText("download_failed")
            if not content.startswith(b"%PDF"):
                warnings.append(f"document {row.doc_id}: response was not a PDF ({len(content)} bytes)")
                return DocText("download_failed")
            self.pdf_cache.put(row.doc_id, content)
        return describe_document(self.pdf_cache.path(row.doc_id), self.max_pdf_pages, self.max_text_chars)
