# API guide for the Flutter side

Live, always-current reference: run the server and open **http://localhost:8000/docs** (schema: `/openapi.json`).
This page is the short version. Plan and rules: `docs/api-plan.md`. Decisions: D10, D11.

## Run it (backend machine)
```
venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```
- Flutter desktop on the same machine: base URL `http://localhost:8000`. From another machine: `http://<backend LAN IP>:8000`
  (and allow port 8000 through the Windows firewall). Keep the base URL in one config value.
- The backend needs `data\snapshots\demo-v3\items.jsonl` (the committed `manifest.json` checks it; see `docs/demo-script.md`)
  and, for prices, the local price cache in `data\cache\prices\`.
- Optional environment variables: `MIZAN_SNAPSHOT` (default `demo-v3`), `MIZAN_OLLAMA_URL` (default `http://localhost:11434`),
  `MIZAN_OLLAMA_MODEL` (default `qwen3:8b`, tag not yet verified on the GPU box), and for the chat call `MIZAN_OLLAMA_NUM_CTX`
  (default 4096), `MIZAN_OLLAMA_TIMEOUT_S` (default 120) and `MIZAN_OLLAMA_SEED` (default 42).
- The server never fetches from PSX while answering a request. Everything is served from the snapshot and local caches.
- No CORS is set up (a Flutter desktop app does not need it). A Flutter web build would.

## Endpoints
| Method and path | Returns |
|---|---|
| `GET /health` | `status` ("ok" or "degraded"), `app_version`, `live_fetching_enabled`, `snapshot` (name, item_count, date_range, tickers, items_by_type, verified), `snapshot_error`, `tickers_error` |
| `GET /tickers` | list of `{ticker, company_name, names, items_in_snapshot, has_data}` |
| `GET /tickers/{ticker}/bundle?as_of=YYYY-MM-DD` | `{ticker, as_of, items:[{id, ticker, source, type, date, text}]}`; `as_of` optional (default: newest date in the snapshot) |
| `GET /evidence/{id}?as_of=` | one item; with `as_of`, an item dated after it is a 404 |
| `GET /tickers/{ticker}/prices?start=&end=&as_of=` | list of `{date, open, high, low, close, volume, is_anomaly}`, oldest first; default is the last 90 days of the cache; `as_of` caps `end` |
| `GET /model/health` | `{reachable, url, configured_model, model_available, parameter_size, quantization, configured_model_loaded, loaded:[{name, size_vram_bytes, expires_at}], latency_ms}` |
| `POST /model/test` (no body) | `{model, parsed:{status, note}, text, timings_ms:{total, load}, tokens_per_second, prompt_tokens, completion_tokens}`: one fixed small prompt, the reply checked against a JSON schema. Timings, speed and counts come from the model server and can be `null` |

`POST /model/test` waits for the model: the first call after the model has been unloaded can take tens of seconds (it is loaded first;
`timings_ms.load` shows how long that took). The server gives up after `MIZAN_OLLAMA_TIMEOUT_S` (default 120 s), so give the UI's HTTP call
a longer timeout than that and show a "waiting for the model" state.

`type` in an item is one of `price`, `financial_results`, `announcement`, `report_section`, `presentation_section`. Item `text` can be long
(announcements and report passages: up to about 2,000 characters). Dates are `YYYY-MM-DD` strings.

## Errors (what the UI should show)
Every error body is `{"detail": "<one readable sentence>"}`: show `detail` as is.

| Status | When |
|---|---|
| 404 | unknown ticker (the message lists the known ones); unknown evidence id, or one not visible as of the date |
| 422 | a bad date (`as_of=banana`), or `start` after `end` |
| 502 | `POST /model/test`: the model answered, but not with JSON matching the schema, even after one retry |
| 503 | the evidence snapshot is missing or does not match its manifest; prices not cached; the model server cannot be reached or did not answer in time; the model is not pulled (the message says which `ollama pull` to run) |

A known ticker with no data returns **200 with an empty `items` list**, not an error. If the backend is stopped, the HTTP call itself fails
(connection refused): the UI should show "backend not reachable" for that case.

## What the UI can show (from api-plan.md's demo flow)
1. Backend status from `/health` (and "degraded" with `snapshot_error` if the data is not usable).
2. Pick a ticker (`/tickers`) and a date; list the bundle's items (date, type, source, id).
3. Move the date earlier: newer items disappear. That is the no-look-ahead rule, visible.
4. Unknown ticker or stopped backend: a clear message, not a crash.
5. Model status from `/model/health` (reachable, loaded, quantization, VRAM), and one structured reply from `POST /model/test`
   (show `parsed.note`, `timings_ms.total` and `tokens_per_second`).

`POST /model/test` was built on 2026-10-16 and is tested with a fake model only; it has not yet been run against the real model.
Not built: `POST /ask` (proposed, see `docs/api-plan.md`).
