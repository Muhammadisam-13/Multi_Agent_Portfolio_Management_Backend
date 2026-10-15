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
| 6 | Gold set (~10 hand-labelled queries -> expected evidence IDs) and a metrics log | **Done on real data**: `eval/gold_demo-v2.json`, 16 queries; BM25 recall@5 0.85, MRR 0.88 (easy 0.94, medium 0.96, hard 0.42). Labels were written after reading titles, so easy/medium are optimistic. |
| 7 | Measure bundle token sizes for the real data; decide whether search is needed or whole bundles fit in context | **Done (estimates)**: bundles are 8k-24k tokens, so they do not fit a small window. Answer: a token-budgeted selection is needed (`select_context`). |
| 8 | Embeddings, only if BM25 recall is insufficient | **Open decision.** BM25 is fine when the question shares words with the item and weak on paraphrases (hard queries 0.42). Embeddings (or stemming / query expansion) would target exactly that; not built. |
| 9 | `mizan/fetcher/`: automated PSX fetchers (rate limit, User-Agent, local cache, live switch), tested against saved responses so the suite never hits PSX | **Done** for the results table and the announcements list with their PDFs (see below) |
| 10 | Loaders and normalizer (`mizan/data/`): prices, macro, PDFs -> text, producing `EvidenceItem` files in `data/snapshots/` | **Partly**: prices, results, announcements, report chunks and snapshot building are done; SBP macro is not |

### What the retrieval layer retrieves today (snapshot `demo-v2`, 6 tickers, 2026-04-13 to 2026-10-12)
| Item type | Source | Count | What an item is |
|---|---|---|---|
| `price` | psxdata (scrapes dps.psx.com.pk, sends PSX's request token) | 738 | one trading day of OHLCV for one ticker |
| `financial_results` | www.psx.com.pk results table | 23 | one company filing: period, profit before/after tax, EPS, dividend text, AGM and book-closure dates |
| `announcement` | dps.psx.com.pk announcements list (D7) + the linked PDF | 131 | title, date, time and the document's text (first 2,000 characters) |
| `report_section` | annual / quarterly / half-yearly report PDFs | 63 | a narrative passage (about 1,800 characters) with its page number |

### Gaps in what is retrieved
- 34 of the 131 announcements are image-only PDFs: kept as title-only items flagged "needs OCR". OCR could not be run on this laptop
  (Windows Application Control blocked the library's DLL; not worked around).
- Report chunks come from a keyword heuristic over the narrative pages; it keeps useful passages but also some climate-disclosure text.
- Two of the 13 periodic reports are image-only (HUBC's and LUCK's March-quarter reports) and yield a single flagged item each.
- No macro data (SBP) yet, so the real snapshot has no MACRO items.
- No news layer (D8).
- ENGRO: prices stop at 2025-01-03, excluded.

### The commands (all run from the local snapshot or cache; live fetching needs `--live`)
- `python -m mizan.fetcher.cli --source announcements --tickers OGDC --from 2026-04-13 --to 2026-10-12 [--live]`
- `python -m mizan.data.build_snapshot --name demo-v2 --tickers OGDC LUCK HBL FFC HUBC SYS --start 2026-04-13 --end 2026-10-12 --announcements --reports`
- `python -m mizan.retrieval.demo --snapshot demo-v2 --ticker OGDC --as-of 2026-09-08 [--compare-as-of D] [--query Q] [--budget N]`
- `python -m mizan.retrieval.sizing --snapshot demo-v2 --as-of 2026-10-12`
- `python -m mizan.retrieval.evaluate --snapshot demo-v2 --gold eval/gold_demo-v2.json`

## Mid demo (2026-10-16)
Seven items, all runnable from cache and snapshots (live PSX calls are not on the critical path); the full list and the checks
behind each are in `docs/mid-and-next-plan.md`. Retrieval covers items 1-4 and 6-7; item 5 is the local model.

## After the mid / still open
1. SBP macro items (needs an API key; decide whether the debate needs it).
2. OCR for the image-only PDFs (another machine, or an engine IT allows).
3. Decide embeddings vs stemming / query expansion for paraphrased questions (step 8), with a larger and harder gold set.
4. Optional news via Tavily or similar (D8).
5. Evidence bundle -> agent turn with evidence-ID citations (thin end-to-end slice); settle the faithfulness method.

## Done means
`pytest` passes on the laptop (CPU only); leakage and isolation tests exist; gold-set metrics are logged to a file; the mid demo
runs end to end from cache and snapshots.
