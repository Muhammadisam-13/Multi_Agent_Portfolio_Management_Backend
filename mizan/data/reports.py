"""Long reports (annual / quarterly) -> a few narrative chunks as EvidenceItems.

A 229-page annual report is far too big to hand to a local model whole, and most of it is financial
statements, notes and governance boilerplate. This module keeps the passages that read like narrative
(reviews, outlook, risks, operations) and drops number tables.

HOW THE SELECTION WORKS (a heuristic, deliberately simple and easy to inspect):
  1. find the narrative zone: from the first page headed as a review / report / message (Chairman,
     Managing Director, CEO, Directors' Report, Management Discussion) to the page before the auditor's
     report, so financial statements and their notes are never searched;
  2. split each page of the zone into chunks of about `target_chars` characters and drop chunks that
     are mostly numbers (tables) or too short to say anything;
  3. score the rest by narrative keywords (outlook, risk, performance, ...) minus boilerplate words
     (committee terms of reference, attendance, ...);
  4. keep the `max_chunks` best, at most `per_page` from one page, in page order.
Every kept chunk records its page number, so a reader can open the PDF and check it. The selection
has no model and no learning in it; if it keeps the wrong pages for a company, the keyword lists
below are the place to tune it.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pymupdf

from mizan.schemas import EvidenceItem

SOURCE = "psx_report"
TYPE = "report_section"

MIN_CHARS = 350                  # shorter chunks are headers, page furniture, signature blocks
MAX_DIGIT_FRACTION = 0.25        # above this share of digits a chunk is a table, not prose (prose with figures sits at 0.01-0.10)

# (pattern, weight): headings and phrases that mark narrative content
POSITIVE = [
    (r"\boutlook\b", 4), (r"\bgoing forward\b|\blooking ahead\b|\bfuture\b", 2),
    (r"\bdirectors['’]? report\b|\bchairman['’]?s? (?:review|message)\b|\b(?:managing director|ceo)['’]?s? (?:review|message)\b", 3),
    (r"\bmanagement discussion\b|\boverview\b|\breview\b", 1),
    (r"\bperformance\b|\bgrowth\b|\bincrease[ds]?\b|\bdecrease[ds]?\b|\bdeclined?\b", 1),
    (r"\brisks?\b|\bchallenges?\b|\bopportunit", 2),
    (r"\bstrategy\b|\bstrategic\b|\bprojects?\b|\bproduction\b|\bdiscover", 1),
    (r"\binflation\b|\binterest rate\b|\bexchange rate\b|\bcommodity\b|\bdemand\b|\bmarket share\b", 2),
    (r"\bdividend\b|\bprofit after tax\b|\brevenue\b|\bsales\b", 1),
]
# boilerplate that fills reports but tells an investor little
NEGATIVE = [
    (r"terms of reference", 3), (r"\battendance\b|\battended\b", 2), (r"code of conduct", 2),
    (r"\bcompliance with\b|\bcode of corporate governance\b", 2), (r"\bannexure\b|\bproxy form\b", 3),
    (r"\bwhistle ?blow", 2), (r"\bdisclaimer\b", 2),
    # climate / ESG disclosure language is keyword-rich (risk, opportunity, demand) but is regulatory detail,
    # not what moves a share price; the review and outlook pages should win
    (r"climate-related|tcfd|scenario analysis|greenhouse|emissions|net.?zero|\besg\b|sustainab", 2),
]


@dataclass(frozen=True)
class Chunk:
    page: int          # 1-based page number in the PDF
    index: int         # chunk number within the page
    text: str
    score: float


def _digit_fraction(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum(c.isdigit() for c in chars) / len(chars) if chars else 1.0


def _score(text: str) -> float:
    low = text.lower()
    pos = sum(w * min(len(re.findall(p, low)), 3) for p, w in POSITIVE)
    neg = sum(w * min(len(re.findall(p, low)), 3) for p, w in NEGATIVE)
    return float(pos - neg)


def _split(text: str, target: int) -> list[str]:
    """Cut text into pieces of about `target` characters at sentence ends."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces, current = [], ""
    for s in sentences:
        if current and len(current) + len(s) > target:
            pieces.append(current)
            current = ""
        current = f"{current} {s}".strip()
    if current:
        pieces.append(current)
    return pieces


REVIEW_HEADING = re.compile(
    r"(chairman|managing director|chief executive|\bceo\b|directors['’]?)\W{0,3}(?:s['’]?\W{0,3})?(review|report|message)"
    r"|management discussion", re.IGNORECASE)
AUDITOR_REPORT = re.compile(r"independent auditor|auditors['’] report", re.IGNORECASE)


def narrative_zone(pages: list[str]) -> tuple[int, int]:
    """(first, last) 0-based page indexes to search: from the first review/report heading to the auditor's report."""
    start = next((i for i, t in enumerate(pages) if REVIEW_HEADING.search(t[:400])), 0)
    end = next((i for i, t in enumerate(pages) if i > start and AUDITOR_REPORT.search(t[:600])), len(pages))
    return start, end - 1


def select_chunks(pdf_path: str | Path, max_chunks: int = 10, target_chars: int = 1800, per_page: int = 2) -> list[Chunk]:
    with pymupdf.open(pdf_path) as doc:
        pages = [" ".join(p.get_text().replace("�", "'").split()) for p in doc]
    first, last = narrative_zone(pages)

    candidates: list[Chunk] = []
    for idx in range(first, last + 1):
        for k, piece in enumerate(_split(pages[idx], target_chars)):
            if len(piece) < MIN_CHARS or _digit_fraction(piece) > MAX_DIGIT_FRACTION:
                continue
            candidates.append(Chunk(idx + 1, k, piece, _score(piece)))

    chosen, per_page_count = [], Counter()
    for c in sorted((c for c in candidates if c.score > 0), key=lambda c: (-c.score, c.page, c.index)):
        if per_page_count[c.page] < per_page:
            chosen.append(c)
            per_page_count[c.page] += 1
        if len(chosen) == max_chunks:
            break
    return sorted(chosen, key=lambda c: (c.page, c.index))


def chunk_items(ticker: str, doc_id: str, day: date, title: str, pdf_path: str | Path,
                max_chunks: int = 10, target_chars: int = 1800) -> list[EvidenceItem]:
    """Narrative chunks of one long report as EvidenceItems dated with the report's announcement date."""
    ticker = ticker.upper()
    label = title.strip().rstrip(".")
    with pymupdf.open(pdf_path) as doc:
        pages = len(doc)
    chunks = select_chunks(pdf_path, max_chunks, target_chars)
    if not chunks:
        return [EvidenceItem(
            id=f"{ticker}-REPORT-{doc_id}-none", ticker=ticker, source=SOURCE, type=TYPE, date=day,
            text=(f"{ticker} report '{label}' (announced {day.isoformat()}, {pages} pages): no narrative passages could be "
                  f"selected from its text layer (it may be scanned and need OCR)."))]
    return [EvidenceItem(
        id=f"{ticker}-REPORT-{doc_id}-p{c.page:03d}-{c.index}", ticker=ticker, source=SOURCE, type=TYPE, date=day,
        text=f"{ticker} report '{label}' (announced {day.isoformat()}), page {c.page} of {pages}: {c.text}")
        for c in chunks]
