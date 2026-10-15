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
| SBP EasyData | Pakistan macro numbers (policy rate, inflation, KIBOR, PKR). **Deferred until after the mid (decision 2026-10-15).** Needs an API key; verify its current docs before building. |
| FRED (fredapi) | Optional global context; skip for now. |
| PSX Data Services / Capital Stake | Paid/licensed; not used now. Mention as the production path. |
| PSX Data Portal announcements (PDFs) | Main narrative source. **Fetched automatically** by the `fetcher` module (rate-limited, cached, switchable). See the compliance note below. |
| News sites, SBP monetary policy statements | After the mid. **No PSX RSS feed exists** (psx.com.pk/psx/news redirects to an HTML articles page; checked 2026-10-13). Outlet feeds or Tavily (decision D8) are options; check what each carries and each site's terms. |

## Pipeline
```
psxdata / PSX announcements fetcher (/ SBP EasyData, news after the mid) -> local cache -> PDF->text + normalizer -> EvidenceItem files -> EvidenceBundle(ticker, as_of) -> FastAPI -> Flutter app
```
The whole path is automatic. The fetcher is a swappable module with a config switch to disable live fetching, so tests and demos
run from cache or snapshots. PDF extraction (PyMuPDF/pdfplumber) is the real work; some PSX documents are scanned and may need OCR.
The portal's announcements page loads its list dynamically; inspect the page's own background requests rather than guessing endpoints,
and expect the page structure to change.

## Compliance note (keep in the report)
PSX's Terms of Use restrict automated retrieval without written permission. Team decision (Isam, 2026-10-13): proceed with
low-volume automated retrieval of public announcements while checking with the supervisor, and email PSX if the supervisor says
it is needed. Guardrails: polite rate limit, project-identifying User-Agent, local cache (download once), live fetching can be
disabled, and raw PSX documents are never committed to git or redistributed.
Later decisions: keep live psxdata price calls (2026-10-13; psxdata attaches a PSX request token, required since 2026-09-24);
the announcements fetcher imitates a browser session (2026-10-15), with no CAPTCHA solving or bypass and no proxy/anti-bot services.

## Retrieval testing (no LLM needed)
- Hard tests: no future-dated items in a bundle; ticker isolation; empty ticker returns an empty bundle without crashing.
- Quality tests: BM25 baseline first, then embeddings only if BM25 falls short. Use a hand-labeled gold set of queries
  and report recall@k and MRR.
- Measure each ticker's bundle size in tokens. With 5-10 tickers and a handful of documents each, a whole bundle may
  fit in the model's context, in which case search-style retrieval is optional; the dated, ID'd bundle design still matters.

## Demo-scale data (initial target)
5-10 tickers across sectors, one fixed as-of date, recent announcements fetched automatically per ticker, daily prices,
frozen into snapshots (SBP macro added after the mid). Tickers: OGDC, LUCK, HBL, FFC, HUBC, SYS (ENGRO dropped 2026-10-15: its prices stop at 2025-01-03; decision D5).

## Open questions
- Final tickers and as-of date; whether a PSX permission email is sent. Mid evaluation: 2026-10-16.
- Exact fields returned by psxdata fundamentals and by SBP EasyData (verify when building the loaders).
