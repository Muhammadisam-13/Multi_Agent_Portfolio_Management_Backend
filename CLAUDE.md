# Mizan — FYP (FAST NUCES Islamabad)

Portfolio management system in the Pakistan Stock Exchange (PSX) context, with an AI decision-support component
(local LLM agents) and a faithfulness evaluation component. Frontend POC (Flutter desktop) already exists.
More project detail will be added later; **do not invent or assume details outside the retrieval layer.**

Team of 3. FYP-1 Mid evaluation is 2026-10-16. Grading summary: @docs/rubric-mid.md.
Retrieval details and constraints: @docs/context.md. Retrieval layer (reported done): @docs/retrieval-plan.md.
Mid plan: @docs/mid-and-next-plan.md. Honest status: @docs/status.md.
**Current task: @docs/api-plan.md** (FastAPI backend so the Flutter UI is connected for the mid).

## Current scope (FYP-1 Mid, updated 2026-10-15; decisions D10, D11 in docs/decisions.md)
1. **PSX retrieval layer:** collects PSX data, normalizes it into dated evidence items, returns an as-of-dated
   bundle for a ticker. Reported done; keep it working and tested.
2. **FastAPI backend API (`api/`):** exposes the retrieval layer (and a model health call) over HTTP so the Flutter
   desktop app can call it. **Required for the mid** (the UI must be connected to the backend).
3. **Local model deployment:** Qwen3-8B via Ollama on the GPU box (Q4_K_M), reached only through the `LLM` interface
   (`mizan/llm/`), visible through the API (`/model/health`).
4. **Model calls and POST /ask (proposed):** a chat call with JSON-schema structured output behind the existing `LLM` interface
   (`OllamaClient` and `FakeLLM`), and a `POST /ask` endpoint that answers a question over an as-of evidence bundle and rejects any
   cited evidence id that is not in that bundle. Owner: Shahzeb. Agreement with Isam: [to confirm]. Tests use `FakeLLM` only; agents,
   debate and the faithfulness layer stay out of scope.
Not in scope before the mid: SBP/macro data (moved to after the mid), agents/debate, faithfulness layer.
The Flutter side and the mid report belong to teammates; the API owner is still to be confirmed (api-plan.md).
If a task needs something outside this scope, ask first.

## Stack
- Python, pytest. Core logic (`mizan/`) is plain Python with no web code. The FastAPI app lives in `api/`,
  imports the core, reuses the existing response types, and runs with uvicorn.
- The API serves from cache/snapshots by default; a UI request never triggers live PSX fetching unless that is
  explicitly enabled in config (and no endpoint built so far has such a path).
- Local LLMs (Ollama, Qwen3-8B on an RTX 3080 10GB box): deployment is part of the mid (see scope). Retrieval itself must
  stay testable with no LLM, and API tests use a fake model.
- Dev laptop has no real GPU; everything in the retrieval layer must run on CPU.

## Contract (`mizan/schemas.py`) — change only with team agreement
- `EvidenceItem`: id (stable, unique), ticker (or "MACRO"), source, type, date, text
- `EvidenceBundle`: ticker, as_of, items

## Hard rules
1. **No look-ahead:** a bundle for `as_of` contains only items with `date <= as_of`. Enforce in code and test (also through the API).
2. **Ticker isolation:** a ticker query returns that ticker's items plus MACRO only.
3. **Automated retrieval of PSX public data is in scope** (no manual PDF downloading as the main path).
   Build it as a swappable `fetcher` module with these guardrails:
   - Polite rate limit (a request every few seconds, configurable), a clear `User-Agent` naming the project,
     and a local cache so each document is downloaded only once.
   - A config switch to disable live fetching (tests and demos run from cache/snapshots).
   - Never commit scraped PDFs or raw PSX data to git (add to `.gitignore`).
   - Note: PSX's Terms of Use restrict automated retrieval without written permission. Team decision
     (Isam, 2026-10-13): proceed with low-volume automated retrieval while checking with the supervisor,
     and email PSX if the supervisor says it is needed. Keep this note in `docs/` and the report.
   - There is no manual PDF drop-folder path. Remove any such code, config and docs if you find them.
   - **Announcements list (dps.psx.com.pk), team decision 2026-10-15 (D7, supersedes D2): a session-imitating fetcher, built on
     2026-10-15** (`mizan/fetcher/announcements.py`) behind the same `fetcher` interface. Limits: load the page as a browser would, read the request token the page
     provides and send it with the list request using the headers the page's own script uses; use Playwright only if the token is
     dynamic JavaScript. Same guardrails as above. **Never solve or bypass reCAPTCHA or any CAPTCHA, and never use proxy or
     anti-bot-bypass services; if the page requires that, stop and record it in `docs/`.**
   - **Tavily (or similar search/extract APIs): optional, news only (D8).** Cache every result with its fetch date and keep only
     items dated on or before `as_of`. Core PSX data must never depend on a third-party search API.
   - **The API never fetches live from a request (D11):** endpoints read the snapshot and caches only.
4. Frozen, versioned snapshots under `data/snapshots/<name>/` so runs are reproducible. Snapshot contents
   (`items.jsonl`, `raw/`) stay local and untracked (they hold PSX data); only each snapshot's `manifest.json`
   (counts, date range, sha256 of the items) is committed, so a teammate can rebuild and verify the same snapshot.
   Decisions and their reasons: `docs/decisions.md`.
5. Keep an AI-usage log (`docs/ai_usage_log.md`); the GenAI-use rubric requires it.

## Repo layout
```
mizan/
  schemas.py
  fetcher/     # automated PSX fetchers (rate-limited, cached, can be switched off); announcements fetcher + dps_session (page token) are built
  llm/         # LLM interface, Ollama client, fake model for tests
  data/        # psxdata loader, pdf_extract.py, reports.py, snapshot writer (SBP loader after the mid)
  retrieval/   # bundle.py (as-of filter), bm25.py, lexical.py, context.py, snapshot store
api/           # FastAPI app for the Flutter frontend (no business logic here)
tests/         # core tests and API tests (FastAPI TestClient)
data/{cache,snapshots}/   # cache git-ignored; snapshots: only manifest.json committed; never commit raw PSX documents
docs/
```

## Working agreements
- Small, frequent commits with meaningful messages; short-lived branches; review before merge
  (the rubric checks commit history from all members).
- Be honest in logs and docs about what is done. Never mark work done that isn't.
- Work on a feature branch; do not commit directly to `main`. Merge only when the team says so.
- Commit messages carry no AI co-author trailer (team decision, 2026-10-15). AI use is disclosed in `docs/ai_usage_log.md` instead.
