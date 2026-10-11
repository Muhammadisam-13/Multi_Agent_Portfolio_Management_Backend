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
| PSX Data Portal announcements (PDFs) | Main narrative source. **Manual drop folder for now** (ToS, see CLAUDE.md rule 3). Teammates are emailing marketdatarequest@psx.com.pk for permission. |
| News sites, SBP monetary policy statements | Saved as text files by hand; check each site's terms. RSS at psx.com.pk/psx/news is a better automation candidate than HTML scraping. |

## Pipeline
```
psxdata / SBP EasyData / PDFs->text / saved news text -> raw cache -> normalizer -> EvidenceItem files -> EvidenceBundle(ticker, as_of)
```
The fetcher is swappable (manual drop folder now, automatic later if permitted). Everything from the drop folder onward is automatic.
PDF extraction (PyMuPDF/pdfplumber) is the real work; some PSX documents are scanned and may need OCR.

## Retrieval testing (no LLM needed)
- Hard tests: no future-dated items in a bundle; ticker isolation; empty ticker returns an empty bundle without crashing.
- Quality tests: BM25 baseline first, then embeddings only if BM25 falls short. Use a hand-labeled gold set of queries
  and report recall@k and MRR.
- Measure each ticker's bundle size in tokens. With 5-10 tickers and a handful of documents each, a whole bundle may
  fit in the model's context, in which case search-style retrieval is optional; the dated, ID'd bundle design still matters.

## Demo-scale data (initial target)
5-10 tickers across sectors, one fixed as-of date, 3-5 curated text items per ticker, SBP policy rate and inflation,
frozen into snapshots. Tickers and the as-of date are not chosen yet.

## Open questions
- Which tickers and as-of date; whether PSX replies to the permission email; mid meeting date.
- Exact fields returned by psxdata fundamentals and by SBP EasyData (verify when building the loaders).
