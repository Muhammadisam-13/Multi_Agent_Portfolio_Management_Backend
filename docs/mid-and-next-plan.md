# Plan: FYP-1 Mid (2026-10-16) and what follows

Decision (Isam, 2026-10-15, agreed with supervisor): the mid shows the **retrieval layer** and **local model deployment**. Nothing else is required for the mid.

## Who does what
- Isam: retrieval layer (to completion) and local model deployment.
- Teammate: mid report.
- Teammate: frontend-to-backend connection (after retrieval exists).
Everyone commits their own work; each person can explain their own part.

## Mid demo (aim for ~10 minutes, all runnable from cache and snapshots; live PSX calls are not on the critical path)
1. Retrieval: for 1-2 tickers, build an as-of bundle and show items, dates, source and stable IDs.
2. Hard rules shown live: a future-dated item is excluded (no look-ahead); another ticker's items never appear (isolation).
3. Failure cases shown honestly: fetch refused or live fetching switched off (falls back to cache, clear message); scanned PDF flagged for OCR; ticker with no data returns an empty bundle, not a crash.
4. Search quality: BM25 over a bundle, with recall@k / MRR from the gold set if it exists by then (say so if it doesn't).
5. Local model: Ollama serving Qwen3-8B (Q4_K_M) on the GPU box, one call that returns schema-valid JSON, with VRAM use and latency noted.
6. Tests: run `pytest` live and show the log.
7. Status slide/section: done, in progress, next, blocked (honest).

## Tonight (priority order)
1. Make sure the demo runs end to end from cache on the laptop. Rehearse it once.
2. `pytest` green; save the log.
3. Local model: model pulled, reachable from the laptop, one structured-output call works, numbers noted.
4. Status doc and decisions doc up to date, including the PSX token / session decision.
5. Give the report teammate: architecture sketch, the EvidenceItem fields, the data-source table, the compliance note, and test results.

## Local model deployment checklist
- Ollama on the GPU box; pull Qwen3-8B (verify the tag and that it is Q4_K_M).
- Reachable from the laptop (LAN `OLLAMA_HOST`, or Tailscale).
- One call with a JSON-schema `format` returning valid JSON; check how Qwen3 thinking mode behaves with structured output and turn it off if needed (verify in the current Ollama docs).
- Fixed seed and low temperature; record VRAM, tokens/sec, latency.
- Keep all calls behind the `LLM` interface so a fake model can stand in for tests.

## After mid
1. PSX announcements fetcher (session-imitating; see below), behind the `fetcher` interface, cached, switchable.
2. Finish the gold set and quality metrics; decide embeddings only if BM25 is not enough.
3. Evidence bundle -> agent turn with evidence-ID citations (thin end-to-end slice).
4. Settle the faithfulness method from the new base paper.

## PSX announcements: session-imitating fetcher
Team decision: imitate a browser session for the announcements list. Approach and limits:
- Load the announcements page as a browser would, read whatever request token the page provides, and send it with the list request, with the headers the page's own script uses.
- If the token is dynamic JavaScript, use a real browser automation tool (Playwright) instead of hand-rebuilding requests.
- Same guardrails as before: low volume, configurable rate limit, project-identifying User-Agent, download once and cache, switch to disable live fetching, nothing raw committed.
- Do not solve or bypass reCAPTCHA or other CAPTCHAs, and do not use proxy or anti-bot-bypass services. If the page requires that, stop and record it.
- Record the decision, date and reasoning in docs/decisions.md and docs/sources-and-compliance.md (PSX terms restrict automated retrieval without permission; token required on data requests since 2026-09-24).

## Tavily (and similar tools)
- Tavily offers Search, Extract (up to 20 URLs per call) and Crawl; free tier is 1,000 credits per month (per its FAQ).
- Not a fix for PSX announcements: it fetches from its own servers, so it does not remove PSX's access check or terms, and it is unlikely to get a token-gated list.
- It is a reasonable optional source for the news layer (finding and extracting articles), with conditions: cache every result with its fetch date; keep only items whose publish date is on or before the as-of date (search results are not date-stable and can leak future content); check whether the API supports date filters; read each source site's terms.
- Keep it behind the fetcher interface and optional. Core PSX data must not depend on a third-party search API, because the handbook's score cap for over-reliance on ready-made APIs/tools applies, and because results must be reproducible.
