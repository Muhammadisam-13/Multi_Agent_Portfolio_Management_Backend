# Narrative sources and compliance decisions (for the report)

Findings from manual checks on 2026-10-13. About 15 polite requests in total (project-naming User-Agent, 4 s between requests).
Raw responses were kept in a scratch folder, not in the repo.

## Decision: announcements list endpoint (dps.psx.com.pk)

- **What the page does:** `https://dps.psx.com.pk/announcements` has no list in its HTML. Its script (`/static/script.js`) loads
  the list with `POST /announcements` (form fields `type`, `symbol`, `query`, `count`, `offset`, `date_from`, `date_to`, `page=annc`)
  and expects an HTML fragment back. The page also loads Google reCAPTCHA.
- **What we got:** a plain POST returned **404**; the same POST with an `X-Requested-With: XMLHttpRequest` header returned **403**.
- **Decision (team, 2026-10-13):** we do **not** imitate a browser session, replay cookies or tokens, or try to get around the
  reCAPTCHA. Work on this endpoint has stopped. Announcement text comes from other sources (below) or is left out and listed as a limitation.
- The fetcher stays behind an interface, with live fetching switchable off; tests, demos and evaluation run from cache and snapshots.

## Terms of Use (read 2026-10-13, https://psx.com.pk/psx/terms-of-use)

Without "prior written permission", the use of "spiders, robots, avatars, agents, tools or other devices" and "systematic retrieval to
create collections, compilations, databases" is prohibited. Without permission only a single copy "for your personal, non-commercial
use only" is allowed. No research exemption was found. The terms define the PSX Website as public pages "including any linked pages owned
and operated by PSX"; they list dps.psx.com.pk among PSX's other sites without saying whether they apply there.
`financials.psx.com.pk` has no terms page and no robots.txt (404); we treat the same terms as applying.
`www.psx.com.pk/robots.txt` disallows only `/cgi-bin/` (robots.txt is not the Terms of Use).
The team decision to proceed with low-volume automated retrieval while checking with the supervisor stands (CLAUDE.md rule 3).

## Source findings

| Source | Finding | Usable? |
|---|---|---|
| `psx.com.pk/psx/news` ("RSS") | Not a feed. It 301-redirects to `/psx/interviews-and-articles`, an HTML page. The only RSS icon in the site HTML is commented out. No feed URL is advertised. | **No RSS exists** as far as we can find. Corrects the earlier assumption in `context.md`. |
| `www.psx.com.pk/psx/announcement/financial-announcements` | One static HTML table, plain GET, no JavaScript or CAPTCHA. Newest first, date group headers (`Oct 12, 2026`), then per row: company *name* (not ticker), time, period (`30/06/2026(YR)`, `(HYR)`, `(IIIQ)`, `(IQ)`), dividend/bonus text, profit before and after tax (Rs. million), EPS, AGM date, book-closure dates. | **Yes, best narrative-style source so far.** Covers only ~6 months (2026-04-13 to 2026-10-12, 1,382 rows). |
| `financials.psx.com.pk` | Page `GET /` works. `POST annQtrStmts.php` (`name=get_comp_data&smbCode=<TICKER>`) returned JSON for OGDC: 47 reports (annual and quarterly) with `period_ended`, `posting_date` and a PDF link (`lib/DownloadPDF.php?id=<id>`). One PDF downloaded: OGDC annual report, 18.7 MB, 229 pages, 1.27 M characters, text layer present (2 near-empty pages). No CAPTCHA seen. | **Yes**, within the team decision. |
| psxdata 1.2.0 `stocks()` | Verified 2026-10-13 for OGDC, HBL, HUBC, 2026-09-01 to 2026-10-13: 31 rows each, newest 2026-10-13, 0 anomalies. | Yes. |

## Things to handle when building on these sources

1. **Financial-results table: company names, not tickers.** Needs a name-to-symbol map (e.g. from psxdata `symbols()`); unmatched names must be reported, not guessed.
2. **Duplicate results per filing:** each period appears twice (consolidated `(CS)` and unconsolidated `(UCS)`), with different numbers and often only one carrying the dividend. Keep both, labelled; do not merge.
3. **`posting_date` on old filings is a bulk upload date:** 14 of OGDC's 47 reports show `2018-12-27`, which is when they were loaded into the portal, not when they were published. For the no-look-ahead rule these items are too late-dated to be trusted (they would hide from earlier as-of dates, or leak if the real date is later). Recent filings look real (quarterlies ~30 days after period end). Use only filings whose posting date is plausible, or restrict the demo to the recent window.
4. **Annual reports are huge:** 1.27 M characters is far beyond a local model's context. They must be split into chunk items (stable ids such as `OGDC-DOC-<id>-p012`) or reduced to selected sections; one item per whole report is not workable.
5. **Time zone and time of day:** the results table has timestamps (e.g. 15:50:52). The schema keeps dates only; an item stamped after market close on the as-of date is treated as available that day. Note this limitation in the report.

## psxdata sends a PSX request token (found 2026-10-13; decided: keep, see decisions.md D3)

While building the results fetcher, `psxdata.symbols()` failed with a 403 whose message mentioned an `X-Req-Id` token. Reading the
library's source (`psxdata/scrapers/token.py`): since 2026-09-24 PSX rejects data (XHR) requests to dps.psx.com.pk with 403 unless they
carry an `X-Req-Id` header equal to a token (`window.__ps._k`) that PSX embeds in its HTML pages. psxdata fetches that token from a PSX
page and attaches it to **every** request, including the price requests used by `mizan/data/prices.py`. `symbols()` still got 403
with the token.

- This is not reCAPTCHA, but it is an access check on the same family of requests as the announcements endpoint that returned 403
  (our plain POST likely lacked this token; not tested, and we are not testing it).
- Price loading (`mizan/data/prices.py`, `fetch_prices`) therefore does what the team decided not to do for the announcements list.
  We had not read `token.py` when the price loader was written and run (2026-10-13, about 6 live calls for OGDC/HBL/HUBC).
- **Decision (Isam, 2026-10-13):** keep live psxdata price calls under conditions: switchable off, fetched once per ticker and
  cached, rate-limited, version pinned and output validated, and a refused token fails loudly. Details and enforcement:
  `docs/decisions.md` D3. `build_snapshot --no-prices` still builds a snapshot without psxdata.
- **Keep this note in the report:** PSX has required the `X-Req-Id` token on data requests since 2026-09-24, and psxdata sends it.

## Financial results fetcher (built 2026-10-13)

`mizan/fetcher/results_table.py` reads the static table at `www.psx.com.pk/psx/announcement/financial-announcements` with plain GET
requests (no token, cookies or special headers), one page per refresh, cached under `data/cache/` (git-ignored).
Live fetching is off by default (`--live` to enable). First live run: 1,381 rows, 2026-04-13 to 2026-10-12.
Conventions: dividend codes such as (F), (D), (i) are passed through verbatim (the page has no legend);
parentheses in profit/EPS cells are rendered as a loss, following the column headers "Profit / (Loss)" and "EPS /(LPS)";
company names map to tickers via `data/ticker_names.json` (currently OGDC, HUBC, HBL only).

## Demo tickers in the results table (checked 2026-10-13 against the cached page fetched 08:19 UTC)

The page covers 2026-04-13 to 2026-10-12. Every company has at most two filing dates in that window (the March quarter in April,
and the June year/half-year in July-September), each usually as an unconsolidated and a consolidated row.

| Ticker | Company name on the page | Rows | Filing dates | Periods |
|---|---|---|---|---|
| OGDC | Oil & Gas Development Company Limited | 4 | 2026-04-29, 2026-09-08 | year to 30 Jun 2026; 3rd quarter to 31 Mar 2026 |
| LUCK | Lucky Cement Limited | 4 | 2026-04-30, 2026-08-10 | year to 30 Jun 2026; 3rd quarter to 31 Mar 2026 |
| HBL | Habib Bank Limited | 4 | 2026-04-17, 2026-08-04 | half year to 30 Jun 2026; 1st quarter to 31 Mar 2026 |
| FFC | Fauji Fertilizer Company Limited | 3 | 2026-04-29, 2026-07-29 | half year to 30 Jun 2026 (one row, no consolidated/unconsolidated tag: labelled "unspecified"); 1st quarter to 31 Mar 2026 |
| HUBC | The Hub Power Company Limited | 4 | 2026-04-22, 2026-08-27 | year to 30 Jun 2026; 3rd quarter to 31 Mar 2026 |
| SYS | Systems Limited | 5 (4 items) | 2026-05-29, 2026-08-27 | half year to 30 Jun 2026; 1st quarter to 31 Mar 2026. One consolidated row was posted twice a second apart; the repeat is dropped |
| ENGRO | **not mapped.** No "Engro Corporation Limited" on the page. Engro companies present: Engro Holdings Limited (4 rows), Engro Polymer & Chemicals, Engro Fertilizers, Engro Powergen Qadirpur, FrieslandCampina Engro Pakistan | - | - | - |

- "Lucky Core Industries Limited" is also on the page; it is a different company from Lucky Cement and is not mapped to LUCK.
- ENGRO is left unmapped rather than guessed: whether the ENGRO symbol now refers to Engro Holdings Limited has not been verified.
- Repeated postings (identical in every field except time) are dropped, keeping the earliest, and reported as a fetcher note: 6 across the whole page on 2026-10-13.
