# Context for the PSX retrieval layer

Project-level details (portfolio side, faithfulness method) are still being settled and will be added later.
Only retrieval-relevant context is recorded here.

## Why retrieval needs more than prices
Numbers alone (OHLCV) give agents little to reason about. The system also needs narrative text (company announcements,
news, central bank statements) as distinct, dated, citable evidence items with stable IDs.

## Data sources (decided triage)
| Source | Use |
|---|---|
| psxdata (PyPI, alpha release) | Primary: historical OHLCV, quotes, fundamentals, KSE-100 constituents, sector summaries. Pin the version; validate outputs (row counts, date ranges). |
| psx-data-reader | Fallback only; known to break silently when PSX changes its HTML. |
| SBP EasyData | Pakistan macro numbers (policy rate, inflation, KIBOR, PKR). Needs an API key; verify its current docs before building. |
| FRED (fredapi) | Optional global context; skip for now. |
| PSX Data Services / Capital Stake | Paid/licensed; not used now. Mention as the production path. |
| PSX filings (financial results table + report PDFs) | Main narrative source. **Fetched automatically** by the `fetcher` module (rate-limited, cached, switchable). The dps.psx.com.pk announcements list is **not used yet** (404/403 on 2026-10-13); a session-imitating fetcher is planned after the mid (decisions.md D7). Sources: www.psx.com.pk financial-announcements table and financials.psx.com.pk. |
| News sites, SBP monetary policy statements | **No RSS feed found** (psx.com.pk/psx/news redirects to an HTML articles page; checked 2026-10-13). Other narrative sources: see docs/sources-and-compliance.md. Check each site's terms. Optional later: Tavily or similar for news only (decisions.md D8). |

## Pipeline
```
psxdata / SBP EasyData / PSX announcements fetcher / news feeds -> local cache -> PDF->text + normalizer -> EvidenceItem files -> EvidenceBundle(ticker, as_of)
```
The whole path is automatic. The fetcher is a swappable module with a config switch to disable live fetching, so tests and demos
run from cache or snapshots. PDF extraction (PyMuPDF/pdfplumber) is the real work; some PSX documents are scanned and may need OCR.
The dps.psx.com.pk announcements list needs PSX's request token; its session-imitating fetcher (decisions.md D7, after the mid) has hard limits: never solve or bypass CAPTCHAs, no proxy or anti-bot services. Expect page structures to change.

## Compliance note (keep in the report)
PSX's Terms of Use restrict automated retrieval without written permission. Team decision (Isam, 2026-10-13): proceed with
low-volume automated retrieval of public announcements while checking with the supervisor, and email PSX if the supervisor says
it is needed. Guardrails: polite rate limit, project-identifying User-Agent, local cache (download once), live fetching can be
disabled, and raw PSX documents are never committed to git or redistributed.

## Retrieval testing (no LLM needed)
- Hard tests: no future-dated items in a bundle; ticker isolation; empty ticker returns an empty bundle without crashing.
- Quality tests: BM25 baseline first, then embeddings only if BM25 falls short. Use a hand-labeled gold set of queries
  and report recall@k and MRR.
- Measure each ticker's bundle size in tokens. With 5-10 tickers and a handful of documents each, a whole bundle may
  fit in the model's context, in which case search-style retrieval is optional; the dated, ID'd bundle design still matters.

## Demo-scale data (initial target)
5-10 tickers across sectors, one fixed as-of date, recent announcements fetched automatically per ticker, SBP policy rate and inflation,
frozen into snapshots. Tickers and the as-of date are not chosen yet.

## Open questions
- Which tickers and as-of date (the financial-results table only covers 2026-04-13 onward, so the as-of date should fall in that window); supervisor's answer on automated retrieval (and whether a PSX email is then needed); mid meeting date.
- Exact fields returned by psxdata fundamentals and by SBP EasyData (verify when building the loaders).

## Verified psxdata 1.2.0 behaviour (2026-10-13)
- `stocks()` returns date, open, high, low, close, volume, is_anomaly, newest first. Whether prices are adjusted for splits/dividends is not yet checked.
- `fundamentals()` is the financial-report filing list (symbol, year, type, period_ended, posting_date, posting_time, document), not ratios; it returned 0 rows outside reporting season.
- psxdata itself requests dps.psx.com.pk, so the compliance note covers it too.
- Announcements list: `POST /announcements` (fields type, symbol, query, count, offset, date_from, date_to, page=annc). A plain POST returned 404 and a POST with `X-Requested-With` returned 403; see decisions.md D7 (decided 2026-10-15, to be built after the mid).
