# Current task: FastAPI backend for the Flutter UI (FYP-1 Mid, 2026-10-16)

Decision (2026-10-15): the UI must be connected to the backend for the mid, otherwise marks are lost. The backend is
exposed as an HTTP API built with FastAPI. SBP/macro data is deferred until after the mid.

## Who does what
- Backend API (`api/`): Isam **[confirm]**.
- Flutter side (calling the API, showing results): frontend teammate **[name]**.
- Agree the endpoint list and response shapes below first; FastAPI's auto-generated docs at `/docs`
  (and the schema at `/openapi.json`) are the shared contract.

## Rules
- `api/` contains no business logic. It calls functions in `mizan/` and returns the existing Pydantic models.
- Serve from cache and snapshots by default. A UI request must never trigger live PSX fetching unless explicitly
  enabled in config.
- Clear errors with proper status codes and a readable message the UI can show.
- Same hard rules as the core: no look-ahead, ticker isolation.

## Minimum endpoints for the mid (build in this order; stop when time runs out)
| # | Method and path | Returns | Errors |
|---|---|---|---|
| 1 | `GET /health` | status, app version, whether live fetching is enabled, snapshot in use | none |
| 2 | `GET /tickers` | configured tickers with company names (from `ticker_names.json`) | none |
| 3 | `GET /tickers/{ticker}/bundle?as_of=YYYY-MM-DD` | `EvidenceBundle` (items dated on or before `as_of`) | 404 unknown ticker; 422 bad date; empty bundle if no data |
| 4 | `GET /evidence/{id}` | one `EvidenceItem` | 404 unknown id |
| 5 | `GET /tickers/{ticker}/prices?start=&end=` | cached daily OHLCV rows | 404 unknown ticker; 503 with message if prices not cached |
| 6 | `GET /model/health` | whether the Ollama endpoint is reachable and which model is loaded | 503 if unreachable |
| 7 | `POST /model/test` (optional; **built 2026-10-16**, tested with a fake model, not yet run against the real model) | one schema-valid structured response from the local model | 503 if unreachable or model not pulled; 502 if output fails schema after one retry |
| 8 | `POST /ask` (**built 2026-10-16**, tested with a fake model, not yet run against the real model) | answer with claims citing evidence ids, plus the evidence used | 404 unknown ticker; 422 bad input; 503 snapshot not usable, model not reachable or not pulled; 502 model output invalid or citing evidence it was not shown, after one retry |

1-3 are the minimum for a connected demo. 6 shows the local model deployment through the same API.

## POST /ask (contract)
**Built 2026-10-16** (`mizan/llm/ask.py`, `api/main.py`; decision D13), at Shahzeb's request. Tested with `FakeLLM` only; not yet run
against the real model. Agreement with Isam: [to confirm]. Agreement with the Flutter side: [to confirm]. Field-by-field guide:
`docs/api-guide.md`.

- Request: `{ticker, as_of, question}`; `as_of` optional (default: the newest date in the snapshot); `question` 1 to 500 characters.
- Response: `{answer, claims: [{text, evidence_ids}], evidence: [EvidenceItem], model, timings_ms: {retrieval, model}}`, plus
  `ticker`, `as_of` (the date used), `cited_ids`, `insufficient_evidence`, `tokens_per_second`, `prompt_tokens`, `completion_tokens`,
  `context: {budget_tokens, used_tokens, dropped}` and `attempts`.
- Errors: 404 unknown ticker; 422 bad input; 503 snapshot not usable, model not reachable or not pulled; 502 model output not
  schema-valid, or citing evidence it was not shown, after one retry (the message names the rejected ids).
- Rules:
  - every cited id must appear in `evidence`; a cited id that is not in the bundle is rejected;
  - `evidence` respects no-look-ahead (date <= `as_of`) and ticker isolation;
  - context is chosen with `select_context` under a token budget;
  - the API never fetches live.

## Running it
- `uvicorn api.main:app --host 0.0.0.0 --port 8000` (use `--reload` while developing).
- Flutter desktop on the same machine calls `http://localhost:8000`; from another machine, use the backend's LAN IP.
- Base URL lives in one config value on the Flutter side.
- Flutter desktop apps are not subject to browser CORS. For a Flutter web build, CORS is enabled (2026-10-16) for
  `http://localhost` and `http://127.0.0.1` on any port, plus any origins in `MIZAN_CORS_ORIGINS`; GET and POST only.
  If the app is built for macOS, the app needs the network client entitlement to make HTTP calls.

## Tests (FastAPI `TestClient`, no network, no GPU)
- `/health` returns 200.
- `/tickers/{ticker}/bundle` with a fixture snapshot: future-dated item absent (no look-ahead through the API).
- Other ticker's items absent (isolation).
- Unknown ticker: 404 with message. Bad date: 422.
- `/model/health` and `/model/test` with a fake model: success path, and an unreachable-model 503.
- `/ask` with a fake model: grounded answer, corrective retry, rejected ids (502), insufficient evidence, no look-ahead and ticker
  isolation checked on everything sent to the model, the token budget, 404, 422, 503. CORS preflights.

## Demo flow in the UI (shows failure cases, which the rubric rewards)
1. Open the app; it shows backend status from `/health`.
2. Pick a ticker and a date; the app shows the evidence list (date, type, source, ID).
3. Move the date earlier: newer items disappear (no look-ahead, visible in the UI).
4. Unknown ticker or backend stopped: the app shows a clear error, not a crash.
5. Model status from `/model/health`; optionally one structured model response.

## Done means
API runs locally, the Flutter app shows a real bundle from it, tests above pass, and every member can explain their part.
