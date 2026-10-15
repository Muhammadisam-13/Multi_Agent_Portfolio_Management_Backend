# Retrieval layer: steps and status

Goal: a tested retrieval layer that returns an as-of-dated `EvidenceBundle` for a ticker. No LLM involved.
Overall plan, demo script and what follows the mid: `docs/mid-and-next-plan.md`. Honest, dated status: `docs/status.md`.
Scope decision (D6, 2026-10-15): the mid (2026-10-16) shows this retrieval layer plus local model deployment. The announcements
fetcher (D7) was built on 2026-10-15, earlier than the plan said; the news layer (D8) is still optional and not built.

## Steps (in order, commit after each) and where each stands on 2026-10-15
| # | Step | Status |
|---|---|---|
| 1 | Repo skeleton and `mizan/schemas.py` (`EvidenceItem`, `EvidenceBundle`) | Done |
| 2 | `tests/fixtures/`: hand-made evidence items (fake tickers and dates, MACRO items, future-dated items) | Done |
| 3 | `mizan/retrieval/bundle.py`: bundle for (ticker, as_of) = ticker or MACRO items with `date <= as_of` | Done |
| 4 | Tests: no leakage, ticker isolation, empty-ticker case | Done |
| 5 | `mizan/retrieval/bm25.py`: BM25 baseline (`rank_bm25`) | Done |
| 6 | Gold set and a metrics log | **Done on real data, two sets.** `eval/gold_demo-v2.json` (16 queries, labels written after reading titles) and `eval/gold_heldout_demo-v3.json` (12 queries, labels found by evidence phrase). See the scores below. |
| 7 | Measure bundle token sizes for the real data; decide whether search is needed or whole bundles fit in context | **Done (estimates)**: bundles are 8.5k-23k tokens at 4 chars/token and 11k-31k at 3 chars/token, so they do not fit a small window. Answer: a token-budgeted selection is needed (`select_context`). |
| 8 | Embeddings, only if BM25 recall is insufficient | **Partly answered.** A lexical fix (stemming + finance abbreviations, `bm25-norm`) lifts recall@5 by 0.04 and 0.09 on the two sets; paraphrases that need real meaning ("money paid out to shareholders" vs "dividend") are still missed. Embeddings can be tried on the GPU box; not built. |
| 9 | `mizan/fetcher/`: automated PSX fetchers (rate limit, User-Agent, local cache, live switch), tested against saved responses so the suite never hits PSX | **Done** for the results table and the announcements list with their PDFs (see below) |
| 10 | Loaders and normalizer (`mizan/data/`): prices, macro, PDFs -> text, producing `EvidenceItem` files in `data/snapshots/` | **Partly**: prices, results, announcements, report and presentation passages and snapshot building are done; SBP macro is not |

### Retrieval scores on snapshot `demo-v3` (recall@5 / MRR; reports in `reports/`)
| Gold set | plain BM25 | normalized BM25 |
|---|---|---|
| original, 16 queries (easy 8, medium 5, hard 3) | 0.83 / 0.85 | **0.87 / 0.86** |
| held-out, 12 queries | 0.69 / 0.71 | **0.78 / 0.74** |

Caveats: the sets are small; the original set's labels were written after reading titles (easy and medium are optimistic); on the
held-out set one query got worse (h11, rank 1 to 3), two still miss, and the abbreviation list was partly motivated by failures
seen on that set, so its gain is not fully independent evidence.

### What the retrieval layer retrieves today (snapshot `demo-v3`, 6 tickers, 2026-04-13 to 2026-10-12, 976 items)
| Item type | Source | Count | What an item is |
|---|---|---|---|
| `price` | psxdata (scrapes dps.psx.com.pk, sends PSX's request token) | 738 | one trading day of OHLCV for one ticker |
| `financial_results` | www.psx.com.pk results table | 23 | one company filing: period, profit before/after tax, EPS, dividend text, AGM and book-closure dates |
| `announcement` | dps.psx.com.pk announcements list (D7) + the linked PDF | 131 | title, date, time and the document's text (up to 2,000 characters) or its opening if long |
| `report_section` | annual / quarterly / half-yearly report PDFs | 60 | a narrative passage (about 1,800 characters) with its page number |
| `presentation_section` | investor briefing slide decks | 24 | a group of consecutive slides (about 1,500 characters) |

### Gaps in what is retrieved
- **45 of the 131 announcements have no usable text** (image-only PDFs: 34 short ones plus 11 long documents that are all images); they
  keep their title and a "needs OCR" note. 22 more have no document on PSX. 39 are fully readable, 13 long documents keep their opening, 1 is
  partly readable, 11 are periodic reports (chunked separately). OCR could not be run on this laptop (Windows Application Control blocked
  the library's DLL; not worked around).
- Two of the 13 periodic reports are image-only (HUBC's and LUCK's March-quarter reports): one flagged item each. LUCK and OGDC have no
  presentation passages.
- Report and slide passages come from keyword heuristics (no model); they keep useful narrative but also some boilerplate.
- No macro data (SBP) yet, so the real snapshot has no MACRO items. No news layer (D8). ENGRO was dropped (D5 update): its prices stop at 2025-01-03.
- Search does not bridge real vocabulary differences (see step 8).

### The commands (all run from the local snapshot or cache; live fetching needs `--live`)
- `python -m mizan.fetcher.cli --source announcements --tickers OGDC --from 2026-04-13 --to 2026-10-12 [--live]`
- `python -m mizan.data.build_snapshot --name demo-v3 --tickers OGDC LUCK HBL FFC HUBC SYS --start 2026-04-13 --end 2026-10-12 --announcements --reports`
- `python -m mizan.retrieval.demo --snapshot demo-v3 --ticker OGDC --as-of 2026-09-08 [--compare-as-of D] [--query Q] [--budget N] [--retriever bm25|bm25-norm]`
- `python -m mizan.retrieval.sizing --snapshot demo-v3 --as-of 2026-10-12`
- `python -m mizan.retrieval.evaluate --snapshot demo-v3 --gold eval/gold_heldout_demo-v3.json --retriever bm25-norm`

## Mid demo (2026-10-16)
Seven items, all runnable from cache and snapshots (live PSX calls are not on the critical path); the full list and the checks
behind each are in `docs/mid-and-next-plan.md`. Retrieval covers items 1-4 and 6-7; item 5 is the local model.

## Still open
1. SBP macro items (needs an API key; decide whether the debate needs it).
2. ~~OCR for the image-only PDFs~~ dropped by decision (D9); scanned notices stay title-only.
3. Embeddings, to be compared with `bm25-norm` on both gold sets (GPU box); a larger and harder gold set.
4. Price granularity (daily rows vs weekly summaries).
5. Optional news via Tavily or similar (D8).
6. Evidence bundle -> agent turn with evidence-ID citations (thin end-to-end slice); settle the faithfulness method.

## Done means
`pytest` passes on the laptop (CPU only); leakage and isolation tests exist; gold-set metrics are logged to a file; the mid demo
runs end to end from cache and snapshots.
