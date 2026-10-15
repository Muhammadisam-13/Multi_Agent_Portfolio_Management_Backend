# Decisions log (retrieval layer)

Each entry: the decision, who made it and when, the reasoning, and how the code enforces it.
Where the reasoning was written up by Claude Code from the session rather than dictated by the team, it says so; the team should
confirm or correct those lines before the report.

## D1. Automated, low-volume retrieval of PSX public pages (Isam, 2026-10-13)
- **Decision:** PSX public announcements and filings are retrieved automatically by a swappable `fetcher`; there is no manual
  PDF drop folder.
- **Reasoning (team):** proceed while checking with the supervisor; email PSX if the supervisor says it is needed.
  PSX's Terms of Use restrict automated retrieval without written permission (see `sources-and-compliance.md`).
- **Enforced by:** `mizan/fetcher/` (rate limit, project User-Agent, cache under git-ignored `data/cache/`, live fetching off by
  default), `.gitignore`.

## D2. Do not get around the dps.psx.com.pk announcements block (Isam, 2026-10-13) - SUPERSEDED by D7 (2026-10-15)
- **Status:** superseded. Kept as history; the reasoning and evidence below are still accurate for 2026-10-13.
- **Decision:** no browser-session imitation, no cookie/token replay, no reCAPTCHA workaround for the announcements list
  (`POST /announcements` returned 404 plain and 403 with an XHR header). Work on that endpoint stopped.
- **Reasoning (team):** stated as the decision; see `sources-and-compliance.md` for the evidence.
- **Consequence:** news-style announcements (board decisions, material information) are not available; this is a stated
  limitation. Narrative comes from the financial results table and, later, report PDFs.

## D3. Keep live psxdata price calls, under conditions (Isam, 2026-10-13)
- **Decision:** keep psxdata for daily prices although it attaches PSX's `X-Req-Id` request token, which PSX has required on
  data requests since 2026-09-24 (`sources-and-compliance.md`).
- **Conditions (team) and how they are enforced** (`mizan/data/prices.py`, `PriceLoader`):
  | Condition | Enforcement |
  |---|---|
  | Behind an interface, live calls switchable off; tests and demos run from cache/snapshots | `FetchConfig.live` (default False); `CacheMiss` if nothing is cached; tests use a fake fetch or monkeypatched psxdata |
  | Fetch each ticker once, cache locally, re-fetch only when asked | full history cached in `data/cache/prices/<TICKER>.csv` + `.json`; `refresh=True` / `--refresh-prices` only |
  | Polite rate limit | shared `Throttle` (default 5 s between live calls); no retries added on top of psxdata's own (max 3 attempts, 1-2 s apart, one token refresh) |
  | Pin the version, validate every fetch | `psxdata==1.2.0` in `requirements.txt` and a runtime check; columns, non-empty, unique dates, plausible range, a refresh may not shrink the history |
  | Fail loudly on a refused token, never silently | `PSXAuthError` -> `BlockedError` naming the token requirement; the run stops; `build_snapshot` prints the reason and writes nothing |
- **Reasoning (written by Claude Code from the session; team to confirm):** prices are needed for the debate layer and no other free
  source was found (PSX Data Services / Capital Stake are paid); with caching the volume is about one request per ticker; the token is
  served in PSX's public HTML pages and psxdata uses it the way the site's own pages do.
- **Open point (updated 2026-10-15):** the inconsistency between D2 and D3 was resolved by D7: the announcements-list fetcher will
  also send the page's token, within limits. The report should say plainly that PSX requires the token on data requests (since
  2026-09-24) and that we send it, for prices through psxdata and later for the announcements list.

## D4. Snapshots stay local; only manifests are committed (Isam, 2026-10-13)
- **Decision:** snapshot contents (`items.jsonl`, `raw/`) are not committed because they contain PSX data; each snapshot's
  `manifest.json` is committed.
- **Reasoning (written by Claude Code from the session; team to confirm):** satisfies both "never commit raw PSX data" and
  "versioned snapshots": the manifest's `items_sha256`, counts and date range let anyone who rebuilds the snapshot from the same
  cache verify it is identical.
- **Enforced by:** `.gitignore` (`data/snapshots/*/*` with `!data/snapshots/*/manifest.json`), CLAUDE.md rule 4.

## D5. Demo tickers (Isam, 2026-10-13)
- **Decision:** OGDC, LUCK, HBL, FFC, HUBC, SYS, ENGRO.
- **Status:** see `sources-and-compliance.md` ("Demo tickers in the results table") for which have usable filings and the open
  ENGRO question.

## D6. Mid scope: retrieval layer and local model deployment (Isam, 2026-10-15, agreed with the supervisor)
- **Decision:** the FYP-1 mid (2026-10-16) shows two things: the **retrieval layer** and **local model deployment**. Nothing else is
  required for the mid.
- **Who does what (from the plan):** Isam: retrieval (to completion) and local model deployment. One teammate: the mid report. One
  teammate: the frontend-to-backend connection, after retrieval exists. Everyone commits their own work and can explain their own part.
- **Mid demo (about 10 minutes, runnable from cache and snapshots, live PSX calls not on the critical path):** an as-of bundle for
  1-2 tickers with items, dates, sources and stable IDs; the hard rules shown live (future item excluded, other tickers never
  appear); failure cases shown honestly (fetch refused or live fetching off -> cache fallback with a clear message, scanned PDF flagged
  for OCR, ticker with no data -> empty bundle); BM25 search with recall@k / MRR from the gold set if it exists (say so if it does not);
  Ollama serving Qwen3-8B (Q4_K_M) returning schema-valid JSON with VRAM and latency noted; `pytest` run live; an honest status
  section. Details: `docs/mid-and-next-plan.md`.
- **Reasoning:** as recorded in the plan; no further reasoning was written down. Faithfulness evaluation, agents and the auditor are
  therefore not part of the mid.
- **Enforced by:** `CLAUDE.md` (scope), `docs/retrieval-plan.md`, `docs/status.md`.

## D7. Session-imitating fetcher for the PSX announcements list (team, 2026-10-15) - supersedes D2
- **Decision:** the team will imitate a browser session to fetch the dps.psx.com.pk announcements list, behind the existing
  `fetcher` interface. The plan said "after the mid"; Isam asked for it to be built now (2026-10-15).
- **Limits (from the plan):**
  - Load the announcements page as a browser would, read whatever request token the page provides, and send it with the list request,
    with the headers the page's own script uses.
  - If the token is produced by dynamic JavaScript, use a real browser automation tool (Playwright) instead of hand-rebuilding requests.
  - Same guardrails as the other fetchers: low volume, configurable rate limit, project-identifying User-Agent, download once and
    cache, a switch that disables live fetching, nothing raw committed to git.
  - **Do not solve or bypass reCAPTCHA or any other CAPTCHA, and do not use proxy or anti-bot-bypass services. If the page requires
    that, stop and record it** in `docs/decisions.md` and `docs/sources-and-compliance.md`.
- **Reasoning:** the plan records this as a team decision without further reasoning. The facts behind it: PSX has required an
  `X-Req-Id` token on data requests since 2026-09-24 (taken from `window.__ps._k` in PSX's HTML pages, per psxdata's source); on
  2026-10-13 our plain POST to `/announcements` returned 404 and the same POST with an XHR header returned 403; D3 already accepts
  sending the same token for prices through psxdata.
- **Risks to state in the report (not hidden):** PSX's Terms of Use restrict automated retrieval without written permission
  (`sources-and-compliance.md`), and this decision knowingly goes further than D1. The announcements page also loads Google
  reCAPTCHA; whether the list request itself depends on a reCAPTCHA token is not known until it is tried, and the stop rule above
  applies if it does. The supervisor's view of this specific decision is not recorded here (the plan records the supervisor's
  agreement on the mid scope, D6).
- **Implementation note for Claude Code:** implement only within these limits; if the page needs a CAPTCHA solution, a proxy or an
  anti-bot service, stop and report instead of working around it.
- **Enforced by:** `mizan/fetcher/dps_session.py` (token, headers, one refresh, then stop with a message naming these limits),
  `mizan/fetcher/announcements.py`, `FetchConfig.live` default False, cache under git-ignored `data/cache/`, 43 tests that never
  hit PSX (fake sessions, generated PDFs, hand-written pages).
- **What was checked before and during the build (2026-10-15):**
  - the page's own script sets `$.ajaxSetup({headers: {"X-Req-Id": window.__ps._k}})`, so the token is the one "the page provides";
    it is a plain variable in the HTML, so Playwright was not needed;
  - the announcements list request has no CAPTCHA field, and reCAPTCHA appears in the site script only on the portfolio register
    and login forms, so the stop condition was not triggered;
  - PSX accepted our project User-Agent (no browser User-Agent was needed) and set no cookies;
  - first live run: a handful of token page loads, 6 list requests (one per ticker) and 109 document downloads at 4 s intervals,
    plus about 6 manual probe requests while building; no refusal.
- **Known gap:** 34 of the 131 announcements fetched are image-only PDFs (no text layer), including many material-information
  notices, board-meeting notices and dividend credits. They are kept as title-only items flagged "needs OCR". An OCR attempt with a
  pip-installable CPU library (rapidocr-onnxruntime) failed on this laptop because Windows Application Control blocked one of its
  DLLs; it was removed and not worked around. Options: OCR on another machine (the GPU box), a different engine such as Tesseract if
  IT policy allows it, or accept title-only items and say so.

## D8. Tavily (or similar) is optional, for news only (Isam, 2026-10-15)
- **Decision:** a search/extract API such as Tavily may be added as an **optional** source for the news layer, behind the `fetcher`
  interface. It is not used for PSX announcements, and nothing in the core PSX data depends on it.
- **What the plan says about Tavily (not verified by Claude Code; check before relying on it):** it offers Search, Extract (up to 20
  URLs per call) and Crawl; the free tier is 1,000 credits per month (per its FAQ).
- **Why not for PSX announcements:** it fetches from its own servers, so it does not remove PSX's access check or terms, and it is
  unlikely to get a token-gated list.
- **Conditions if used:**
  - cache every result with its fetch date;
  - keep only items whose publish date is on or before the as-of date (search results are not date-stable and can leak future content);
  - check whether the API supports date filters;
  - read each source site's terms.
- **Reasoning (from the plan):** core PSX data must not depend on a third-party search API, both because the handbook caps the score
  for over-reliance on ready-made APIs and tools, and because results must be reproducible.
- **Enforced by:** not built yet.
