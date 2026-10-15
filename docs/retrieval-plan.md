# PSX retrieval layer plan (reported done as of 2026-10-15)

Status: PSX data retrieval is reported done. Verify each step against the repo and tests before claiming it in the report.
SBP macro (part of step 10) is deferred until after the mid. The current task is now @docs/api-plan.md.

Goal: a tested retrieval layer that returns an as-of-dated `EvidenceBundle` for a ticker. No LLM involved.

## Steps (in order, commit after each)
1. Repo skeleton and `mizan/schemas.py` (`EvidenceItem`, `EvidenceBundle`). Push first so teammates can build against it.
2. `tests/fixtures/`: ~10-15 hand-made evidence items with fake dates and tickers, including MACRO items and one future-dated item.
3. `mizan/retrieval/bundle.py`: build a bundle for (ticker, as_of): ticker or MACRO items with `date <= as_of`.
4. Tests: no leakage, ticker isolation, empty-ticker case.
5. `mizan/retrieval/bm25.py`: BM25 baseline (`rank_bm25`) over a bundle's items.
6. Gold set (start with ~10 hand-labeled queries -> expected evidence IDs) and a test that logs recall@5 and MRR to a file.
7. Measure bundle token sizes for the real data; decide whether search is needed or whole bundles fit in context.
8. Only if BM25 recall is insufficient: add embeddings (check current small embedding models, e.g. bge-m3, nomic-embed-text) and compare to BM25.
9. `mizan/fetcher/`: automated PSX announcements fetcher (rate limit, User-Agent, local cache, config switch to disable live fetching).
   Test it against saved responses so the test suite never hits PSX.
10. Loaders and normalizer (`mizan/data/`): psxdata prices/fundamentals, SBP macro (after the mid), cached PDFs -> text, all producing `EvidenceItem` files in `data/snapshots/`.

Steps 1-6 can run on fake data right away; steps 9-10 plug real data in.

## Done means
`pytest` passes on the laptop (CPU only); leakage and isolation tests exist; gold-set metrics are logged to a file.
