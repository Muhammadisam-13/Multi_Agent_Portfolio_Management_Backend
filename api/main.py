"""FastAPI app for the Flutter UI. Run:  uvicorn api.main:app --host 0.0.0.0 --port 8000

Interactive docs at /docs, machine-readable contract at /openapi.json.
Every endpoint reads the verified snapshot or the local caches; none of them fetches from PSX (decision D11).
"""

from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api import __version__
from api.config import Settings
from api.models import Health, SnapshotSummary, TickerOut
from mizan.data.tickers import TickerInfo, load_tickers
from mizan.retrieval.store import SnapshotError, SnapshotStore, resolve_snapshot_folder
from mizan.schemas import EvidenceBundle


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="Mizan retrieval API",
        version=__version__,
        description="Evidence bundles for PSX tickers, as of a date. Serves a frozen snapshot; never fetches live.",
    )
    app.state.settings = settings

    # Both are loaded once at startup. A failure does not stop the server: /health reports it and the endpoints that
    # need the data answer 503 with the reason, so the UI can show it.
    try:
        app.state.store = SnapshotStore.load(resolve_snapshot_folder(settings.snapshot, settings.snapshots_dir))
        app.state.snapshot_error = None
    except SnapshotError as exc:
        app.state.store, app.state.snapshot_error = None, str(exc)
    try:
        app.state.tickers = {t.ticker: t for t in load_tickers(settings.ticker_names_path)}
        app.state.tickers_error = None
    except (OSError, ValueError) as exc:
        app.state.tickers, app.state.tickers_error = {}, f"ticker list not usable: {exc}"

    # --- shared dependencies ----------------------------------------------------------
    def get_store(request: Request) -> SnapshotStore:
        if request.app.state.store is None:
            raise HTTPException(503, f"Evidence snapshot is not usable: {request.app.state.snapshot_error}")
        return request.app.state.store

    def get_tickers(request: Request) -> dict[str, TickerInfo]:
        if request.app.state.tickers_error:
            raise HTTPException(503, request.app.state.tickers_error)
        return request.app.state.tickers

    def known_ticker(ticker: str, tickers: dict[str, TickerInfo] = Depends(get_tickers)) -> str:
        symbol = ticker.strip().upper()
        if symbol not in tickers:
            raise HTTPException(404, f"Unknown ticker '{ticker}'. Known tickers: {', '.join(sorted(tickers))}.")
        return symbol

    # Readable 422s: one sentence the UI can show instead of FastAPI's list of error objects.
    @app.exception_handler(RequestValidationError)
    async def readable_validation_error(request: Request, exc: RequestValidationError):
        parts = [f"{' '.join(str(p) for p in e['loc'][1:]) or e['loc'][0]}: {e['msg']}" for e in exc.errors()]
        hint = " Dates must look like YYYY-MM-DD." if any(e["type"].startswith("date") for e in exc.errors()) else ""
        return JSONResponse(status_code=422, content={"detail": "Invalid request: " + "; ".join(parts) + "." + hint})

    # --- 1. health ----------------------------------------------------------------------
    @app.get("/health", response_model=Health, tags=["status"])
    def health(request: Request) -> Health:
        state = request.app.state
        degraded = state.store is None or state.tickers_error is not None
        return Health(
            status="degraded" if degraded else "ok",
            app_version=__version__,
            live_fetching_enabled=settings.live_fetching_enabled,
            snapshot=SnapshotSummary(**state.store.summary()) if state.store else None,
            snapshot_error=state.snapshot_error,
            tickers_error=state.tickers_error,
        )

    # --- 2. tickers ---------------------------------------------------------------------
    @app.get("/tickers", response_model=list[TickerOut], tags=["evidence"])
    def tickers(request: Request, configured: dict[str, TickerInfo] = Depends(get_tickers)) -> list[TickerOut]:
        store = request.app.state.store
        out = []
        for info in configured.values():
            count = store.item_count_for(info.ticker) if store else None
            out.append(TickerOut(ticker=info.ticker, company_name=info.company_name, names=list(info.names),
                                 items_in_snapshot=count, has_data=bool(count)))
        return out

    # --- 3. bundle ----------------------------------------------------------------------
    @app.get("/tickers/{ticker}/bundle", response_model=EvidenceBundle, tags=["evidence"])
    def bundle(
        ticker: str = Depends(known_ticker),
        as_of: date | None = Query(None, description="YYYY-MM-DD. Items dated after it are excluded. Default: the newest date in the snapshot."),
        store: SnapshotStore = Depends(get_store),
    ) -> EvidenceBundle:
        """The ticker's evidence dated on or before `as_of` (plus MACRO items). A known ticker with no data gives an empty list."""
        return store.bundle(ticker, as_of or store.latest_date() or date.today())

    return app


app = create_app()
