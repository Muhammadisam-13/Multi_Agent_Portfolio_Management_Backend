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

## D2. Do not get around the dps.psx.com.pk announcements block (Isam, 2026-10-13)
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
- **Open point to raise with the supervisor:** D2 and D3 treat similar PSX access checks differently (D2 does not send a token for
  the announcements list; D3 lets psxdata send one for prices). The team accepted this; the report should say so plainly.

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
