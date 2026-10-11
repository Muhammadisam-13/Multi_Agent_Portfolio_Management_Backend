# Current task: PSX retrieval layer

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
9. Loaders and normalizer (`mizan/data/`): psxdata prices/fundamentals, SBP macro, PDF -> text from the drop folder, all producing `EvidenceItem` files in `data/snapshots/`.

Steps 1-6 can run on fake data right away; step 9 plugs real data in once teammates' loaders exist.

## Done means
`pytest` passes on the laptop (CPU only); leakage and isolation tests exist; gold-set metrics are logged to a file.
