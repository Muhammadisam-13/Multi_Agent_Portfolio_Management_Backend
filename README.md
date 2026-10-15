# Mizan backend

Backend for **Mizan**, our FYP (FAST NUCES Islamabad): portfolio decision support for the Pakistan Stock Exchange (PSX).
This repo holds two things:

1. **The PSX retrieval layer** (`mizan/`): collects PSX data, turns it into dated evidence items, and returns an *as-of* bundle for a
   ticker (only what was public on or before a date).
2. **A FastAPI backend** (`api/`): exposes that data over HTTP so the Flutter app can show it.

The local model (Qwen3-8B on Ollama) runs on a separate GPU machine; the API only checks that it is reachable.

---

## 1. Set up (Windows, about 10 minutes)

You need **Python 3.12** and **git**.

```powershell
git clone https://github.com/Muhammadisam-13/Multi_Agent_Portfolio_Management_Backend.git backend
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

`psxdata` pulls in some large packages, so the install takes a few minutes and needs internet.

### Get the data (not in git)
PSX data is never committed (team rule). Ask Isam for **`mizan-demo-data.zip`** (about 380 KB) and unzip it **into the `backend` folder**, so
that you end up with:

```
backend\data\snapshots\demo-v3\items.jsonl      <- the 976 evidence items
backend\data\cache\prices\                      <- daily prices (CSV + JSON per ticker)
```

The committed `data\snapshots\demo-v3\manifest.json` holds a hash of `items.jsonl`, so a damaged or wrong file is refused instead of being
served. **Never commit anything under `data\`** (`.gitignore` already blocks it).

---

## 2. Run the API

From the `backend` folder:

```powershell
venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Then open:
- **http://localhost:8000/health**: should show `"status":"ok"` and the snapshot `demo-v3` with 976 items.
- **http://localhost:8000/docs**: every endpoint, with a "Try it out" button. This page is the contract between the backend and the app.

Add `--reload` while you are changing backend code. Stop the server with `Ctrl+C`.

### Endpoints (full details: `docs/api-guide.md`)
| Method and path | What it gives |
|---|---|
| `GET /health` | backend status, version, the snapshot in use |
| `GET /tickers` | the six tickers with company names |
| `GET /tickers/{ticker}/bundle?as_of=YYYY-MM-DD` | the ticker's evidence dated on or before `as_of` |
| `GET /evidence/{id}` | one evidence item |
| `GET /tickers/{ticker}/prices?start=&end=` | daily prices (open, high, low, close, volume) |
| `GET /model/health` | whether the Ollama model server answers (503 if not, which is expected on a laptop without it) |

Try: http://localhost:8000/tickers/OGDC/bundle?as_of=2026-09-08 and then the same with `as_of=2026-09-01`. The annual results
(announced 8 Sep) disappear. That is the "no look-ahead" rule, and it is the core of the demo.

Every evidence item has the same six fields: `id`, `ticker`, `source`, `type`, `date`, `text`.

---

## 3. Connecting the Flutter app

- **Base URL:** `http://localhost:8000` when the app and the backend run on the same machine. From another machine on the same network:
  `http://<backend machine's IP>:8000`, and allow inbound port 8000 in Windows Firewall on the backend machine.
  Keep the base URL in **one** config value in the app.
- **Errors:** every error comes back as `{"detail": "<one readable sentence>"}`. Show `detail` as it is.
  - 404: unknown ticker (the message lists the valid ones) or unknown evidence id
  - 422: bad input, e.g. a date not in `YYYY-MM-DD` format
  - 503: the data or the model server is not available (the message says why)
  - connection refused: the backend is not running. Show "backend not reachable".
- A ticker with no data returns **200 with an empty list**, not an error.
- A Flutter **desktop** build needs no CORS settings. A Flutter **web** build would, and a **macOS** build needs the network-client entitlement.

### What the demo should show in the app (from `docs/api-plan.md`)
1. Backend status from `/health`.
2. Pick a ticker (`/tickers`) and a date: list the evidence (date, type, source, id).
3. Move the date earlier: newer items disappear.
4. Unknown ticker, or backend stopped: a clear message, not a crash.
5. Model status from `/model/health`.

---

## 4. Run the tests

```powershell
venv\Scripts\python.exe -m pytest -q
```

313 tests, a few seconds, no internet, no GPU. They use small fake data, so they pass even without the data zip.

There is also a terminal walkthrough of the retrieval layer: `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Pause`
(see `docs/demo-script.md`).

---

## 5. If something goes wrong

| Symptom | Cause and fix |
|---|---|
| `/health` says `"degraded"` and `snapshot_error` says a file is missing | the data zip is not unzipped in the right place; check `data\snapshots\demo-v3\items.jsonl` exists |
| `snapshot_error` says the hash does not match the manifest | the `items.jsonl` file is damaged or from another snapshot; unzip it again |
| `/tickers/{ticker}/prices` gives 503 "not cached" | `data\cache\prices\` is missing; unzip the data again |
| `/model/health` gives 503 | normal unless the Ollama server is running and reachable (`MIZAN_OLLAMA_URL`, default `http://localhost:11434`) |
| `ModuleNotFoundError: No module named 'api'` or `'mizan'` | run commands from the `backend` folder, using `venv\Scripts\python.exe` |
| port 8000 already in use | another server is running; stop it or use `--port 8001` (and change the app's base URL) |
| the app on another machine cannot connect | start with `--host 0.0.0.0`, check the IP, allow port 8000 in Windows Firewall |
| `scripts\demo.ps1` is blocked | run it with `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1` |

Optional settings (environment variables): `MIZAN_SNAPSHOT` (default `demo-v3`), `MIZAN_OLLAMA_URL`, `MIZAN_OLLAMA_MODEL` (default
`qwen3:8b`). The API **never fetches from PSX** while answering a request; it only reads the local data.

---

## 6. What is in the repo

```
api/        FastAPI app (no business logic, it calls mizan/)
mizan/      the core: schemas.py (EvidenceItem, EvidenceBundle), fetcher/ (PSX fetchers), data/ (prices, PDFs, snapshots),
            retrieval/ (as-of bundles, search, the snapshot store), llm/ (model interface, Ollama client)
tests/      all tests (fixtures are hand-made fake data, never real PSX data)
scripts/    demo.ps1, the terminal demo
docs/       plans, decisions, status (see below)
data/       local only: snapshots and caches (git-ignored except snapshot manifests)
```

### The data, in one paragraph
Six tickers (OGDC, LUCK, HBL, FFC, HUBC, SYS), 2026-04-13 to 2026-10-12, 976 items: daily prices, PSX financial results, company
announcements with their PDF text, and passages from annual / quarterly reports and investor presentations. It is a one-time pull: nothing
refreshes automatically. Not included yet: macro data (SBP, after the mid) and text for the 45 announcements that are scanned images
(no OCR, by decision).

### Read next
- `docs/api-guide.md`: the endpoints and responses in detail (for the app)
- `docs/status.md`: what is done, what is not, known limits
- `docs/decisions.md`: why things are the way they are (D1-D11)
- `docs/sources-and-compliance.md`: where the data comes from and the PSX Terms of Use note
- `docs/demo-script.md`: the terminal demo

## Team rules (short)
- Work on a feature branch; do not commit directly to `main`. Merge when the team agrees.
- Never commit anything under `data\` except snapshot `manifest.json` files.
- Be honest in docs and logs about what is done.
