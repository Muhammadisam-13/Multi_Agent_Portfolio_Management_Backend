# Plan: FYP-1 Mid (2026-10-16) and what follows

Updated 2026-10-15 (evening). The mid shows:
1. **PSX retrieval layer** (reported done; verify against tests).
2. **FastAPI backend connected to the Flutter UI** (required; without the UI connection marks are lost). See docs/api-plan.md.
3. **Local model deployment** (Qwen3-8B via Ollama), reachable through the API.
SBP/macro data is **deferred until after the mid**. Agents, debate and the faithfulness layer are shown as design and plan only.

## Who does what
- Isam: retrieval layer, backend API **[confirm API owner]**, local model deployment.
- Teammate: mid report.
- Teammate: Flutter side of the frontend-to-backend connection.
Everyone commits their own work; each person can explain their own part.

## Mid demo (aim for ~10 minutes, all from cache and snapshots; live PSX calls are not on the critical path)
1. Start the API; the Flutter app shows backend status.
2. In the app: pick a ticker and a date; the evidence list from the as-of bundle appears (date, type, source, ID).
3. Hard rules visible in the UI: move the date earlier and newer items disappear (no look-ahead); only that ticker's items appear (isolation).
4. Failure cases shown honestly: unknown ticker or stopped backend gives a clear error in the app; live fetching off falls back to cache; scanned PDF flagged; empty ticker returns an empty list, not a crash.
5. Local model: model status through the API (`/model/health`), optionally one schema-valid structured response, with VRAM and latency noted.
6. Tests: run `pytest` (core and API tests) live and show the log.
7. Status section: done, in progress, next, blocked (honest).

## Tonight (priority order)
1. API endpoints 1-3 from docs/api-plan.md working and tested; share `/docs` with the Flutter teammate.
2. Flutter app calling the API and showing a real bundle. Rehearse the demo once end to end.
3. `pytest` green (core + API); save the log.
4. Local model: pulled, reachable, `/model/health` works, one structured-output call, numbers noted.
5. Status and decisions docs up to date (UI-connection decision, SBP deferral, PSX token / session decisions).
6. Give the report teammate: architecture (now including the API and UI), EvidenceItem fields, endpoint list, data-source table, compliance note, test results.

## Local model deployment checklist
- Ollama on the GPU box; pull Qwen3-8B (verify the tag and that it is Q4_K_M).
- Reachable from the backend machine (LAN `OLLAMA_HOST`, or Tailscale).
- One call with a JSON-schema `format` returning valid JSON; check how Qwen3 thinking mode behaves with structured output and turn it off if needed (verify in the current Ollama docs).
- Fixed seed and low temperature; record VRAM, tokens/sec, latency.
- Keep all calls behind the `LLM` interface so a fake model can stand in for tests.

## After mid
1. SBP EasyData macro loader (policy rate, inflation) producing MACRO evidence items.
2. PSX announcements fetcher (session-imitating; see below), behind the `fetcher` interface, cached, switchable, if not already complete.
3. Finish the gold set and quality metrics; decide embeddings only if BM25 is not enough.
4. Evidence bundle -> agent turn with evidence-ID citations (thin end-to-end slice), exposed through the API.
5. Settle the faithfulness method from the new base paper.
6. Extend the UI: portfolio views and AI output.

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
