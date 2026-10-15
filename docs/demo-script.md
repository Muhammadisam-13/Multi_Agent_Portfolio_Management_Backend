# Demo script: the retrieval layer (mid, 2026-10-16)

The retrieval demo is a **terminal demo**. It runs from one local file, needs no internet, no GPU and no model, and takes about 10
minutes. The local model (Qwen3-8B on Ollama) is shown **separately** and is not connected to the retrieval layer yet.
Dry run done on 2026-10-15: all 14 steps run, 247 tests pass.

## Run it

On this laptop, from the `backend` folder:

```
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Pause     # presenting: waits for Enter between steps
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1            # everything at once
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Only 3    # one step
```

Every step prints a yellow `SAY:` line: that is what to tell the supervisor.

### On another machine
1. Python 3.12, then in the `backend` folder: `python -m venv venv` and `venv\Scripts\pip install -r requirements.txt`
   (`psxdata` pulls in large packages, so allow a few minutes and a connection).
2. Copy **one file**: `data\snapshots\demo-v3\items.jsonl` (476 KB) to the same path. It is not in git because it holds PSX data; the
   committed `manifest.json` next to it checks the file, so a damaged or edited copy is refused. Nothing else is needed (the 226 MB `data\cache`
   is only for rebuilding snapshots).
3. `git pull` the branch `retrieval/fetcher-and-search`, then run the script.

## The 14 steps

| # | Step | What it shows |
|---|---|---|
| 1 | Tests | 247 automated tests pass; none touches PSX |
| 2 | As-of bundle, OGDC on 8 Sep | items with date, source, type, stable ID |
| 3 | No look-ahead | going from 1 Sep to 8 Sep, the annual results appear; before 8 Sep they do not exist |
| 4 | Ticker isolation | HBL's bundle contains only HBL items |
| 5 | Unknown ticker | an explained empty bundle, no crash |
| 6 | Search | ranked, dated, cited results for "oil and gas discovery" |
| 7 | Search limit | "money paid out to shareholders" gets wrong hits (keyword search, not meaning) |
| 8 | Token budget | what a small model would receive and what was left out |
| 9 | Bundle sizes | 8.5k-23k tokens (estimated), why step 8 exists |
| 10 | Search quality | recall and MRR, plain vs stemmed search, two gold sets |
| 11 | Failure: nothing cached, live off | a clear message, not a silent empty result |
| 12 | Failure: PSX refuses | simulated by tests: one token refresh, then a stop that names the limits |
| 13 | Failure: scanned notice | the item keeps its title and says "needs OCR" |
| 14 | Failure: tampered snapshot | one changed byte and the demo refuses the file |

## Say these things out loud (they are true and the docs say them)
- Data: prices (psxdata), PSX results table, company announcements and their PDFs, report and investor-presentation passages; 6 tickers,
  976 items, 2026-04-13 to 2026-10-12. It is a one-time pull; nothing refreshes automatically.
- PSX's Terms of Use restrict automated retrieval without written permission. The team decided to proceed at low volume (decisions D1, D3, D7);
  the guardrails are a rate limit, a project User-Agent, a cache, a switch that turns live fetching off, and no raw data in git.
- Not built: macro data (so there are no MACRO items yet), OCR (45 of 131 announcements are image-only and keep only their title),
  embeddings. Search matches words, not meaning.
- The model is not reading this evidence yet. Evidence in, cited answer out is the next step.
- Gold-set labels were written by the assistant and the first set after reading titles, so the scores are optimistic and the sets are small.

## For the teammate who owns the UI

1. **There is no API.** The retrieval layer is Python code run from a terminal. There is no server, so the Flutter app cannot call it yet. The
   plan puts the frontend-to-backend connection *after* retrieval exists; the mid demo does not need it.
2. **For the mid, the UI needs nothing from the backend.** Show the terminal demo and, separately, the UI as it is.
3. **After the mid**, the connection is a thin web wrapper (FastAPI, which `CLAUDE.md` plans for later) around two existing functions.
   It needs team agreement first (the project scope currently says no API). It would take a question and return items:

   Request: `{"ticker": "OGDC", "as_of": "2026-09-08", "query": "oil and gas discovery", "budget_tokens": 3000}`

   Response: a list of items, each with exactly these six fields (the team-agreed contract in `mizan/schemas.py`):
   ```json
   {"id": "OGDC-ANN-282420", "ticker": "OGDC", "source": "psx_announcements", "type": "announcement",
    "date": "2026-09-09", "text": "OGDC announcement on 2026-09-09 at 9:16 AM: Material Information. ..."}
   ```
   plus counts of what the two rules left out. `type` is one of `price`, `financial_results`, `announcement`, `report_section`,
   `presentation_section`; item `text` is long for announcements and report passages (up to about 2,000 characters).
4. The backend runs on CPU, in Python 3.12, and reads one local file. It needs no GPU and no internet. The data folder is git-ignored; do not commit it.
5. Questions about what the data is: `docs/status.md` and `docs/retrieval-plan.md`.
