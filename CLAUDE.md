# Mizan — FYP (FAST NUCES Islamabad)

Portfolio management system in the Pakistan Stock Exchange (PSX) context, with an AI decision-support component
(local LLM agents) and a faithfulness evaluation component. Frontend POC (Flutter desktop) already exists.
More project detail will be added later; **do not invent or assume details outside the retrieval layer.**

Team of 3. FYP-1 Mid evaluation is ~2 weeks from 2026-10-09. Grading summary: @docs/rubric-mid.md.
Retrieval details and constraints: @docs/context.md. **Current task: @docs/retrieval-plan.md.**

## Current scope: backend, PSX retrieval layer only
Build a Python package that collects PSX data, normalizes it into dated evidence items, and returns an
as-of-dated bundle for a given ticker. Nothing else is in scope yet (no agents, no auditor, no API, no frontend work).
If a task needs something outside this scope, ask first.

## Stack
- Python, pytest. Core logic is plain Python with no web code. FastAPI wrapper comes later.
- Local LLMs (Ollama, Qwen3-8B on an RTX 3080 10GB box) come later. Retrieval must be testable with no LLM.
- Dev laptop has no real GPU; everything in the retrieval layer must run on CPU.

## Contract (`mizan/schemas.py`) — change only with team agreement
- `EvidenceItem`: id (stable, unique), ticker (or "MACRO"), source, type, date, text
- `EvidenceBundle`: ticker, as_of, items

## Hard rules
1. **No look-ahead:** a bundle for `as_of` contains only items with `date <= as_of`. Enforce in code and test.
2. **Ticker isolation:** a ticker query returns that ticker's items plus MACRO only.
3. **Automated retrieval of PSX public announcements is in scope** (no manual PDF downloading as the main path).
   Build it as a swappable `fetcher` module with these guardrails:
   - Polite rate limit (a request every few seconds, configurable), a clear `User-Agent` naming the project,
     and a local cache so each document is downloaded only once.
   - A config switch to disable live fetching (tests and demos run from cache/snapshots).
   - Never commit scraped PDFs or raw PSX data to git (add to `.gitignore`).
   - Note: PSX's Terms of Use restrict automated retrieval without written permission. Team decision
     (Isam, 2026-10-13): proceed with low-volume automated retrieval while checking with the supervisor,
     and email PSX if the supervisor says it is needed. Keep this note in `docs/` and the report.
   - There is no manual PDF drop-folder path. Remove any such code, config and docs if you find them.
4. Frozen, versioned snapshots under `data/snapshots/` so runs are reproducible.
5. Keep an AI-usage log (`docs/ai_usage_log.md`); the GenAI-use rubric requires it.

## Repo layout (retrieval scope)
```
mizan/
  schemas.py
  fetcher/     # automated PSX announcements fetcher (rate-limited, cached, can be switched off)
  data/        # psxdata + SBP loaders, pdf_extract.py, normalizer.py
  retrieval/   # bundle.py (as-of filter), bm25.py, embeddings.py (only if needed)
tests/
data/{cache,snapshots}/   # cache is git-ignored; never commit raw PSX documents
docs/
```

## Working agreements
- Small, frequent commits with meaningful messages; short-lived branches; review before merge
  (the rubric checks commit history from all members).
- Be honest in logs and docs about what is done. Never mark work done that isn't.
