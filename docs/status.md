# Status (updated 2026-10-20, after the FYP-1 mid; older sections from 2026-10-15 below)

Written by Claude Code from the repository and test runs on 2026-10-15; Isam to correct anything that is out of date.
Nothing here is marked done unless it exists in the repo and is tested. Scope: `docs/mid-and-next-plan.md` (decision D6).

## After the mid (written 2026-10-20 on branch `docs/post-mid-status`, from `origin/main` at `ac2b73f`)

**Verified 2026-10-20:** on `main`'s code, `pytest -q` gives **448 passed, 2 skipped** (the skipped ones are the opt-in live-model
tests, `MIZAN_LIVE_OLLAMA=1`). Nothing below is marked done unless it exists on `main` and those tests cover it.

### What was demoed at the mid (2026-10-16)
- **[Isam to fill in: what was actually shown, and the supervisor's feedback.]** Not recorded by the assistant; it was not told.
- What was prepared: the presentation and report source (`Mizan_FYP1_Mid_Presentation.pptx`, `Mizan_FYP1_Mid_Report_LaTeX_Source.zip`,
  commit `05e691f`); the terminal demo `scripts/demo.ps1` (14 steps, `c99f34f`); the API with `/docs`; a local page of real outputs
  for screenshots (`demo-outputs/mizan-retrieval-outputs.html`, outside the repo, not committed: it quotes PSX documents).

### Working and tested (on `main`)
| Part | Where | Key commits |
|---|---|---|
| Retrieval layer: fetchers (results table, announcements with the page token, prices via psxdata), PDF text, report and slide passages, snapshots with manifests, as-of bundles (no look-ahead, ticker isolation), plain and normalized BM25, context selector, gold sets | `mizan/` | merged in `0730a38`; snapshot `demo-v3` manifest `b51fd33`; normalized search `eec8a34` |
| API endpoints 1-6 (`/health`, `/tickers`, `/tickers/{t}/bundle`, `/evidence/{id}`, `/tickers/{t}/prices`, `/model/health`) | `api/` | `9c24520`, `5166938` |
| `OllamaClient.chat` with JSON-schema output, endpoint 7 `POST /model/test` | `mizan/llm/`, `api/` | `fab0bbf`, `6cc57fc` (Shahzeb) |
| `ask()` and endpoint 8 `POST /ask` (grounded answer, rejected ids, 2500-token budget, D13), CORS for localhost | `mizan/llm/ask.py`, `api/` | `363c40e`, `bee05de`, `a3d6a3f`, merged as PR #1 `ac2b73f` (Shahzeb) |

### Half-done
- **`POST /ask` on the real model:** the first real run (2026-10-16, `qwen3:4b-instruct` on the Mac, context 4096) failed (reply cut off at
  512 tokens). The fix (`9c63c87`, `3bde136`, `4f3df48`, `16cad2d`) is tested with fakes only and **not yet re-run on the real model**.
- **`POST /model/test`** has not been run against the real model. The target model `qwen3:8b` on the GPU box is unverified (D12).
- **Flutter connection:** state not known to the assistant. **[Isam to confirm whether the app was connected for the mid.]**
- **`README.md`** (set-up and run guide, `5d692b2`) is only on branch `retrieval/fetcher-and-search`, **not on `main`**.
- Open [confirm] items in the plan: the API owner; agreement on the `/ask` contract with Isam and the Flutter side.
- Gold-set labels (`eval/`) were written by the assistant and are not reviewed. The AI-usage log's "reviewed / changed" column is blank.

### Known problems and limits
- 45 of 131 announcements are image-only and carry only their title (no OCR, D9); 22 more have no document on PSX.
- No MACRO items: SBP is deferred (D10). Search matches words, not meaning (held-out recall@5 0.78 with normalized BM25).
- Bundles are 8.5k-23k tokens (estimate); `/ask` works under a 2500-token budget. A full-length retry may still exceed a 4096 context (D13).
- The data is a one-time pull (prices to 2026-10-13, announcements to 2026-10-15); nothing refreshes (D16). It is not in git; it is shared
  as a zip (D17). Live PSX calls rely on PSX's request token, and PSX's Terms of Use restrict automated retrieval (D1, D3, D7).
- Windows Application Control on the development laptop blocks some native libraries (it stopped the OCR attempt).
- Full test runs occasionally take 1-2 minutes instead of seconds on the laptop (seen 2026-10-15/16); the tests themselves are fast.

### Note on older sections
The sections below were written on 2026-10-15. The "Note on the working copy" bullet is resolved: those doc edits were committed in `0e56e69`.

## Scope change (evening of 2026-10-15; decisions D10 and D11)
- The Flutter UI must be connected to the backend for the mid, so a **FastAPI backend (`api/`) is now required**. SBP/macro is **deferred until
  after the mid**. PSX retrieval is reported done. Plan: `docs/api-plan.md`.
- **API status (2026-10-15, night): endpoints 1-6 of `docs/api-plan.md` are built and tested** in `api/` (38 TestClient tests, 313 tests in total pass).
  Checked once over HTTP with a real uvicorn server against the real snapshot and caches. Guide for the Flutter side: `docs/api-guide.md`.
  - `GET /health`, `/tickers`, `/tickers/{ticker}/bundle`, `/evidence/{id}`, `/tickers/{ticker}/prices`, `/model/health`.
  - No request fetches from PSX (a test fails if any endpoint talks to a non-local host).
  - **Built 2026-10-16:** the chat call with JSON-schema output (`OllamaClient.chat`, one retry on bad output) and endpoint 7
    `POST /model/test`. Tested with fakes only (fake HTTP session, `FakeLLM`); **not yet run against the real model**. An opt-in live
    test exists (`tests/test_llm_live.py`, `MIZAN_LIVE_OLLAMA=1`).
  - **Built 2026-10-16:** `ask()` (`mizan/llm/ask.py`) and endpoint 8 `POST /ask`: an answer over the as-of evidence, cut to a
    2500-token budget, with every cited id checked against the evidence shown (one corrective retry, then 502; D13). CORS for a Flutter
    web build on localhost. Tested with `FakeLLM` (439 tests passed, 2 opt-in live tests skipped). Contract agreement with Isam and the
    Flutter side: [to confirm].
  - **First real run, 2026-10-16 (Shahzeb, `qwen3:4b-instruct` on Ollama, context 4096): `POST /ask` failed** with "the reply was cut
    off at the 512-token limit" on both attempts. Fix on the same day (D13 update): output cap is now a setting,
    `MIZAN_OLLAMA_NUM_PREDICT` (default 1024); the prompt asks for at most 2 sentences and 3 one-sentence claims; retries no longer
    resend the bad reply (it did not fit the 4096 context); the end of an unusable reply goes to the server log. Tested with fakes
    (`FakeLLM`, and the real `OllamaClient` over a fake HTTP session for cut-off replies): 448 tests pass, 2 opt-in live tests
    skipped. **Not yet re-run against the real model**, so it is not known yet whether the answers now fit; at the pessimistic 3
    characters per token a retry with a full-length reply is still about 50 tokens over 4096 (arithmetic in D13).
  - **Update 2026-10-15:** the Ollama client has now been checked once against a real Ollama (health check only, over the LAN, from
    Windows; D12): `/model/health` returned reachable true, model_available true, about 55 ms, with `qwen3:4b-instruct` on a MacBook M1.
    The chat call and `/ask` (2026-10-16) have not been run against it yet. The default model tag `qwen3:8b` (the target on
    the GPU box) is still unverified.
  - **Not done by me:** the Flutter side (teammate), the model deployment itself (Isam), who owns the API (marked [confirm] in the plan).
  - The sections below describe the retrieval layer and were written before this change; the demo-item table still lists the terminal demo,
    which remains a fallback. The UI demo flow is in `docs/api-plan.md`.
- Still to confirm: who owns the API; the Flutter teammate's name (both marked [confirm] in the plan).
- Note on the working copy: uncommitted edits to `docs/context.md`, `docs/mid-and-next-plan.md` and `docs/retrieval-plan.md` (the new plan wording)
  are untouched; `docs/retrieval-plan.md` in the working copy no longer holds the status tables committed earlier (they are in git history).

## Verified today
- Work is on branch `retrieval/fetcher-and-search`. 247 tests pass on the laptop (CPU only, about 3 s). `main` holds an earlier merge.
- Local snapshot `demo-v3` (976 items, 6 tickers, 2026-04-13 to 2026-10-12) was built offline from the local caches and verifies against its
  committed manifest. Its contents and the caches exist only on this laptop (untracked by design, D4); a fresh clone cannot run the
  demo without a copy of `data/` or live fetches with `--live`. Older snapshots `demo-v1` and `demo-v2` have manifests too.
- The announcements fetcher ran live once for six tickers: 6 list requests and 109 document downloads at 4 s intervals, no refusal.
- Update 2026-10-15: `mizan/llm` exists (health check; a chat call was added on 2026-10-16, tested with fakes only). Ollama is not
  installed on this laptop; the development model runs on a MacBook over the LAN (D12).

## What is retrieved (see `docs/retrieval-plan.md` for the table)
Daily prices (738), PSX financial-results rows (23), company announcements with their PDF text (131), narrative passages from
annual / quarterly / half-yearly reports (60) and from investor presentations (24), for OGDC, LUCK, HBL, FFC, HUBC, SYS.
Each is a dated `EvidenceItem` with a stable ID.

## Mid demo items (from the plan) and where each stands
| # | Demo item | Status | What is missing |
|---|---|---|---|
| 1 | As-of bundle for 1-2 tickers showing items, dates, source, stable IDs | **Done**: `python -m mizan.retrieval.demo --snapshot demo-v3 --ticker OGDC --as-of 2026-09-08` | nothing: `scripts\demo.ps1` runs all 14 steps (dry run 2026-10-15); guide in `docs/demo-script.md`; rehearse it once |
| 2 | Hard rules live: future item excluded, other tickers never appear | **Done**: the same command prints what rule 1 and rule 2 left out; `--compare-as-of 2026-09-01` shows the annual result appearing between two dates | the real snapshot has **no MACRO items** (SBP not built), so MACRO inclusion is shown on fixtures only |
| 3 | Failure cases shown honestly | **Implemented and tested with fakes**: refused fetch falls back to the cached page with a warning, a second refusal stops with a message naming the D7 limits; live off + empty cache gives a clear `CacheMiss`; changed page gives `StructureChangedError`; scanned PDF flagged "needs OCR" (45 real examples in the data); unknown ticker gives an explained empty bundle; a tampered snapshot is refused | a real PSX refusal cannot be forced on demand; show it with the tests (`pytest tests/test_dps_session.py -v`) |
| 4 | BM25 search with recall@k / MRR | **Done on real data**, two gold sets, plain and normalized BM25 (table below) | say that the sets are small, the first set's labels were written after reading titles, and BM25 is weak on paraphrases |
| 5 | Local model: Ollama + Qwen3-8B (Q4_K_M), one schema-valid JSON call, VRAM and latency noted | **The call is in the repo (`POST /model/test`, 2026-10-16) but tested with fakes only; not yet run against a real model.** Isam to fill in from the GPU box | a real run (Mac 4B first, then the 8B on the GPU box, labelled by model tag, D12); VRAM and latency figures; the Ollama checklist in the plan |
| 6 | `pytest` run live | **Ready** (247 pass) | save the log |
| 7 | Status section | **This file** | Isam to review |

Search quality on `demo-v3` (recall@5 / MRR):

| Gold set | plain BM25 | normalized BM25 (default in the demo and the selector) |
|---|---|---|
| original, 16 queries | 0.83 / 0.85 | 0.87 / 0.86 |
| held-out, 12 queries | 0.69 / 0.71 | 0.78 / 0.74 |

Also useful in the demo: `... --query "oil and gas discovery" --budget 3000` shows what a model with 3,000 tokens of room would
receive and what was left out; `python -m mizan.retrieval.sizing --snapshot demo-v3 --as-of 2026-10-12` shows why (bundles are 8.5k-23k
tokens at 4 characters per token, 11k-31k at 3; estimates, not a real tokenizer).

## Retrieval layer by component
**Done and tested**
- Schemas, as-of/ticker-isolated bundle builder, plain and normalized BM25, recall@k / MRR, two real-data gold sets, evaluation command.
- Fetcher core: rate limit, project User-Agent, retries with backoff, page cache, live switch (off by default), typed failures; POST and file downloads.
- Financial results table fetcher and normalizer (`www.psx.com.pk`).
- Announcements fetcher (`dps.psx.com.pk`, decision D7): the page's own request token, paging, per-page cache, PDFs downloaded once;
  documents classified as readable / partly scanned / scanned / long, long ones keep their opening.
- Narrative passages from periodic reports (contents-aware zone, heuristic scoring) and from investor slide decks.
- psxdata price loader with local cache, version pin, validation, loud failure on a refused token (D3).
- Snapshot writer, `verify_snapshot`, `build_snapshot` command; manifests committed.
- Bundle size estimates and a token-budgeted context selector (`select_context`).

**Known limits (say them out loud)**
- **Bundles do not fit a small window** (see above) and 17-48% of their characters are daily price rows. The selector exists for that;
  the choice of price granularity (daily rows vs weekly summaries) is still open.
- **45 of 131 announcements are image-only** and carry only their title; many are material-information, board-meeting and dividend notices.
  22 more have no document. OCR could not be run on this laptop (Windows Application Control blocked the library; not worked around).
  Two periodic reports are image-only too.
- **Search handles word forms and standard abbreviations, not meaning.** "Money paid out to shareholders" does not find the dividend items.
  Embeddings are the next test (GPU box); not built.
- Report and slide passages come from keyword heuristics and still contain some boilerplate; the results table covers about 6 months.
- Announcement dates are the dates PSX shows (time of day is kept in the text, not used by the as-of filter).
- Live PSX calls rely on PSX's request token (required since 2026-09-24): psxdata sends it for prices (D3), our announcements fetcher sends it (D7).
  PSX's Terms of Use restrict automated retrieval without written permission (`docs/sources-and-compliance.md`).
- Nothing refreshes automatically; data is a one-time pull (prices to Oct 13, results page Oct 13, announcements Oct 15). Isam decided refreshing during
  a decision is not needed.

**Not started**
- SBP macro (MACRO items); optional news via Tavily (D8); embeddings; the `LLM` interface and local model deployment (D6).
- OCR: decided not to do it (D9).

**Blocked / unresolved**
- Nothing is blocked by an outside party. ENGRO was dropped on 2026-10-15 (D5 update): its prices stop at 2025-01-03.
- The AI-usage log's "reviewed / changed" column is still blank for every entry.
