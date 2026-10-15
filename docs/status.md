# Status (as of 2026-10-15, the day before the FYP-1 mid on 2026-10-16)

Written by Claude Code from the repository and test runs on 2026-10-15; Isam to correct anything that is out of date.
Nothing here is marked done unless it exists in the repo and is tested. Scope: `docs/mid-and-next-plan.md` (decision D6).

## Verified today
- Work is on branch `retrieval/fetcher-and-search`. 214 tests pass on the laptop (CPU only, about 2 s). `main` holds an earlier merge.
- Local snapshot `demo-v2` (955 items, 6 tickers, 2026-04-13 to 2026-10-12) was built offline from the local caches and verifies against its
  committed manifest. Its contents and the caches exist only on this laptop (untracked by design, D4); a fresh clone cannot run the
  demo without a copy of `data/` or live fetches with `--live`.
- The announcements fetcher ran live once for six tickers: 6 list requests and 109 document downloads at 4 s intervals, no refusal.
- No LLM or Ollama code is in the repo; Ollama is not installed on this laptop.

## What is retrieved (see `docs/retrieval-plan.md` for the table)
Daily prices (738), PSX financial-results rows (23), company announcements with their PDF text (131) and narrative passages from
annual / quarterly / half-yearly reports (63), for OGDC, LUCK, HBL, FFC, HUBC, SYS. Each is a dated `EvidenceItem` with a stable ID.

## Mid demo items (from the plan) and where each stands
| # | Demo item | Status | What is missing |
|---|---|---|---|
| 1 | As-of bundle for 1-2 tickers showing items, dates, source, stable IDs | **Done**: `python -m mizan.retrieval.demo --snapshot demo-v2 --ticker OGDC --as-of 2026-09-08` | nothing; rehearse it |
| 2 | Hard rules live: future item excluded, other tickers never appear | **Done**: the same command prints what rule 1 and rule 2 left out; `--compare-as-of 2026-09-01` shows the annual result appearing between two dates | the real snapshot has **no MACRO items** (SBP not built), so MACRO inclusion is shown on fixtures only |
| 3 | Failure cases shown honestly | **Implemented and tested with fakes**: refused fetch falls back to the cached page with a warning, a second refusal stops with a message naming the D7 limits; live off + empty cache gives a clear `CacheMiss`; changed page gives `StructureChangedError`; scanned PDF flagged "needs OCR" (34 real examples in the data); unknown ticker gives an explained empty bundle; a tampered snapshot is refused | a real PSX refusal cannot be forced on demand; show it with the tests (`pytest tests/test_dps_session.py -v`) |
| 4 | BM25 search with recall@k / MRR | **Done on real data**: 16 labelled queries, recall@5 0.85, MRR 0.88 (easy 0.94, medium 0.96, hard 0.42); `python -m mizan.retrieval.evaluate --snapshot demo-v2 --gold eval/gold_demo-v2.json` | say that the labels were written after reading titles, so easy/medium scores are optimistic and BM25 is weak on paraphrases |
| 5 | Local model: Ollama + Qwen3-8B (Q4_K_M), one schema-valid JSON call, VRAM and latency noted | **Not in this repo and not verified here.** Isam to fill in from the GPU box | `LLM` interface and a fake model for tests; the Ollama checklist in the plan |
| 6 | `pytest` run live | **Ready** (214 pass) | save the log |
| 7 | Status section | **This file** | Isam to review |

Also useful in the demo: `python -m mizan.retrieval.demo ... --query "oil and gas discovery" --budget 3000` shows what a model with 3,000
tokens of room would receive and what was left out; `python -m mizan.retrieval.sizing --snapshot demo-v2 --as-of 2026-10-12` shows why.

## Retrieval layer by component
**Done and tested**
- Schemas, as-of/ticker-isolated bundle builder, BM25 baseline, recall@k / MRR, real-data gold set and evaluation command.
- Fetcher core: rate limit, project User-Agent, retries with backoff, page cache, live switch (off by default), typed failures; POST and file downloads.
- Financial results table fetcher and normalizer (`www.psx.com.pk`).
- Announcements fetcher (`dps.psx.com.pk`, decision D7): the page's own request token, paging, per-page cache, PDFs downloaded once.
- Report narrative chunking (heuristic, see the module docstring) for annual / quarterly / half-yearly reports.
- psxdata price loader with local cache, version pin, validation, loud failure on a refused token (D3).
- Snapshot writer, `verify_snapshot`, `build_snapshot` command; manifests for `demo-v1` and `demo-v2` committed.
- Bundle size estimates and a token-budgeted context selector (`select_context`).

**Known limits (say them out loud)**
- **Bundles are 8k-24k tokens (estimated, not a real tokenizer)** and 22-67% of that is daily price rows; they do not fit a small window.
  The selector exists for that; the choice of price granularity (daily rows vs weekly summaries) is still open.
- **34 of 131 announcements are image-only PDFs** and carry only their title; many are material-information, board-meeting and dividend notices.
  OCR could not be run on this laptop (Windows Application Control blocked the library; not worked around). Two periodic reports are image-only too.
- **BM25 does not handle paraphrases** (hard queries 0.42). Embeddings or query expansion would be the next step; not built.
- The report chunker is a keyword heuristic over narrative pages; it keeps useful passages but still lets some climate-disclosure text in.
- The results table covers about 6 months; announcement dates are the dates PSX shows (time of day is kept in the text, not used by the as-of filter).
- Live PSX calls rely on PSX's request token (required since 2026-09-24): psxdata sends it for prices (D3), our announcements fetcher sends it (D7).
  PSX's Terms of Use restrict automated retrieval without written permission (`docs/sources-and-compliance.md`).

**Not started**
- SBP macro (MACRO items); optional news via Tavily (D8); embeddings; OCR; the `LLM` interface and local model deployment (D6).

**Blocked / unresolved**
- Nothing is blocked by an outside party. ENGRO has no usable symbol (its prices stop at 2025-01-03) and is excluded.
- The AI-usage log's "reviewed / changed" column is still blank for every entry.
