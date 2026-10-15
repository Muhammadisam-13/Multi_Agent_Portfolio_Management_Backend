# Status (as of 2026-10-15, the day before the FYP-1 mid on 2026-10-16)

Written by Claude Code from the repository and a test run on 2026-10-15; Isam to correct anything that is out of date.
Nothing here is marked done unless it exists in the repo and is tested. Scope: `docs/mid-and-next-plan.md` (decision D6).

## Verified today
- Work is on branch `retrieval/fetcher-and-search` (this status describes that branch). `main` / `origin/main` hold an earlier merge
  of the same work at `3789082`; the snapshot line-ending fix is on both. 109 tests pass on the laptop (CPU only, 1-45 s per run).
- Local snapshot `demo-v1` (761 items: 6 tickers, 23 results items + 738 daily price items, 2026-04-13 to 2026-10-12) verifies against its
  committed manifest. Its contents and the fetch cache exist only on this laptop (untracked by design, D4).
- No LLM or Ollama code is in the repo; Ollama is not installed on this laptop.

## Mid demo items (from the plan) and where each stands
| # | Demo item | Status | What is missing |
|---|---|---|---|
| 1 | As-of bundle for 1-2 tickers showing items, dates, source, stable IDs | **Works in code and tests**; checked by hand on `demo-v1` | No command or script that builds and prints a bundle for a (ticker, as_of); today it takes ad-hoc Python |
| 2 | Hard rules live: future item excluded, other tickers never appear | **Tested** (fixtures with future-dated items; checked on real data on 2026-10-13) | A live way to show it on the real snapshot (e.g. the same ticker at two as-of dates; OGDC as of 2026-09-01 vs 2026-09-08). Real snapshot has no MACRO items, so MACRO inclusion is only shown on fixtures |
| 3 | Failure cases shown honestly | **Implemented and tested with fakes**: refused fetch falls back to the cached page with a warning; live off + empty cache raises a clear `CacheMiss`; changed page raises `StructureChangedError`; scanned PDF flagged `needs_ocr`; unknown ticker gives an empty bundle | A runnable way to trigger each one on demand (no real refusal can be forced); no real scanned PSX PDF seen yet, so the OCR flag is shown on a generated PDF |
| 4 | BM25 search, with recall@k / MRR if a gold set exists | **BM25 done.** Gold set exists only over fake fixtures: recall@5 0.70, MRR 0.70 | No gold set over real data, no token-size measurement (plan step 7); say so on the slide |
| 5 | Local model: Ollama + Qwen3-8B (Q4_K_M), one schema-valid JSON call, VRAM and latency noted | **Not in this repo and not verified here.** Isam to fill in from the GPU box | `LLM` interface and a fake model for tests; the Ollama checklist in the plan |
| 6 | `pytest` run live | **Ready** (109 pass) | Save the log (the plan asks for it) |
| 7 | Status section | **This file** | Isam to review |

Not required for the demo but asked in the plan: an end-to-end rehearsal from cache, and material for the report teammate (architecture
sketch, `EvidenceItem` fields, data-source table, compliance note, test results). Existing: field list in `mizan/schemas.py` and
`CLAUDE.md`, data-source table in `docs/context.md`, compliance notes in `docs/sources-and-compliance.md` and `docs/decisions.md`.
Missing: an architecture sketch and a saved pytest log.

## Retrieval layer by component
**Done and tested**
- Schemas, as-of/ticker-isolated bundle builder, BM25 baseline, metrics (recall@k, MRR) and a gold-set test on fixtures.
- Fetcher core: rate limit, project User-Agent, retries with backoff, page cache, live switch (off by default), typed failures.
- Financial results table fetcher and normalizer (`www.psx.com.pk`): 1,375 rows after dropping repeats; real runs on 2026-10-13.
- psxdata price loader with local cache, version pin, validation, loud failure on a refused token (D3); live fetch done for 7 tickers.
- Snapshot writer, `verify_snapshot`, `build_snapshot` command; `demo-v1` manifest committed.
- PDF text extraction with scanned-page flagging (tested on generated PDFs only).

**In progress / partly done**
- Gold set: fixtures only. Real-data gold set not written.
- Report PDFs from `financials.psx.com.pk`: format checked once by hand (OGDC annual report, 229 pages, text layer present); no fetcher,
  no section selection, no chunking.

**Not started**
- Token-size measurement of real bundles (plan step 7); embeddings decision (step 8).
- SBP macro (MACRO items). Whether it is needed is to be decided after the first demo.
- Announcements-list fetcher (D7) and optional Tavily news (D8): both are after the mid.
- LLM interface and local model deployment (D6): nothing in this repo yet.

**Blocked / unresolved**
- Nothing is blocked by an outside party today.
- ENGRO has no usable symbol: its psxdata prices stop at 2025-01-03 and "Engro Corporation" is not on the results page; it is excluded from
  `demo-v1`. The demo uses OGDC, LUCK, HBL, FFC, HUBC, SYS (decision D5).

## Limits to say out loud
- Each ticker has only 3-4 financial-results items in the 6-month window the results table covers; the rest of its bundle is daily price items.
  Price items dominate bundle size, which has not been measured.
- No news-style announcements until D7 is built; the narrative is results rows only.
- The demo data lives on one laptop (cache and snapshot contents are git-ignored). A clone cannot run the demo without either a copy of
  `data/` or live fetches with `--live`.
- Live PSX calls rely on PSX's request token (required since 2026-09-24); see D3, D7 and `docs/sources-and-compliance.md`.
- The AI-usage log's "reviewed / changed" column is still blank for every entry.
