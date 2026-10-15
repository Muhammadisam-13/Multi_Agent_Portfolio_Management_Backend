# Retrieval layer: steps and status

Goal: a tested retrieval layer that returns an as-of-dated `EvidenceBundle` for a ticker. No LLM involved.
Overall plan, demo script and what follows the mid: `docs/mid-and-next-plan.md`. Honest, dated status: `docs/status.md`.
Scope decision (D6, 2026-10-15): the mid (2026-10-16) shows this retrieval layer plus local model deployment; the PSX
announcements-list fetcher (D7) and the news layer (D8) come after the mid.

## Steps (in order, commit after each) and where each stands on 2026-10-15
| # | Step | Status |
|---|---|---|
| 1 | Repo skeleton and `mizan/schemas.py` (`EvidenceItem`, `EvidenceBundle`) | Done |
| 2 | `tests/fixtures/`: hand-made evidence items (fake tickers and dates, MACRO items, future-dated items) | Done |
| 3 | `mizan/retrieval/bundle.py`: bundle for (ticker, as_of) = ticker or MACRO items with `date <= as_of` | Done |
| 4 | Tests: no leakage, ticker isolation, empty-ticker case | Done |
| 5 | `mizan/retrieval/bm25.py`: BM25 baseline (`rank_bm25`) | Done |
| 6 | Gold set (~10 hand-labelled queries -> expected evidence IDs) and a test that logs recall@5 and MRR to a file | Partly: 10 queries over the fake fixtures, logged (recall@5 0.70, MRR 0.70). No gold set over real data yet. |
| 7 | Measure bundle token sizes for the real data; decide whether search is needed or whole bundles fit in context | Not started |
| 8 | Only if BM25 recall is insufficient: embeddings (check current small models, e.g. bge-m3, nomic-embed-text) and compare to BM25 | Undecided until step 6 has a real-data gold set |
| 9 | `mizan/fetcher/`: automated PSX fetchers (rate limit, User-Agent, local cache, config switch to disable live fetching), tested against saved responses so the suite never hits PSX | Partly (see below) |
| 10 | Loaders and normalizer (`mizan/data/`): psxdata prices, SBP macro, PDFs -> text, all producing `EvidenceItem` files in `data/snapshots/` | Partly (see below) |

### Step 9 in parts
- 9a. Financial results table (`www.psx.com.pk`, plain GET): **done**, tested with a fake session and a hand-written page; one live run on 2026-10-13.
- 9b. Report PDFs from `financials.psx.com.pk` (annual and quarterly reports): not built. Reports are large (the OGDC annual report is
  229 pages), so they need section selection and chunking into evidence items, and scanned pages flagged for OCR.
- 9c. **After the mid:** announcements-list fetcher for dps.psx.com.pk, session-imitating with the limits in D7 (no CAPTCHA solving
  or bypass, no proxy or anti-bot services; stop and record if the page needs that), behind the `fetcher` interface, cached, switchable.
- 9d. **After the mid, optional:** news via Tavily or similar (D8), news only, date-filtered to `as_of`, cached with fetch dates.

### Step 10 in parts
- psxdata prices: **done** (local cache, pinned version, validation, loud failure on a refused token; live fetch done 2026-10-13).
- Results-table normalizer, snapshot writer, `verify_snapshot`, `build_snapshot` command: **done**; snapshot `demo-v1` manifest committed
  (its contents stay local, decision D4).
- PDF -> text: `extract_text` with scanned-page flagging is done and tested on generated PDFs; not yet connected to a fetcher or to chunking.
- SBP macro (MACRO items): not started. Decide after the first demo whether it is needed.

## Mid demo (2026-10-16)
Seven items, all runnable from cache and snapshots (live PSX calls are not on the critical path); the full list and the checks
behind each are in `docs/mid-and-next-plan.md`. Retrieval covers items 1-4 and 6-7; item 5 is the local model.

## After the mid (order from the plan)
1. Announcements-list fetcher (9c).
2. Finish the gold set and quality metrics (steps 6-8); embeddings only if BM25 is not enough.
3. Evidence bundle -> agent turn with evidence-ID citations (thin end-to-end slice).
4. Settle the faithfulness method from the new base paper.

## Done means
`pytest` passes on the laptop (CPU only); leakage and isolation tests exist; gold-set metrics are logged to a file; the mid demo
runs end to end from cache and snapshots.
