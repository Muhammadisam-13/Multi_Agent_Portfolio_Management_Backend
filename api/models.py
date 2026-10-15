"""Response shapes that are specific to the API (the evidence types come from mizan/schemas.py)."""

from pydantic import BaseModel


class SnapshotSummary(BaseModel):
    name: str
    item_count: int
    date_range: list[str] | None          # [first, last] item date
    tickers: list[str]
    items_by_type: dict[str, int]
    created_utc: str | None
    verified: bool                         # checked against its committed manifest at startup


class Health(BaseModel):
    status: str                            # "ok", or "degraded" when the snapshot or ticker list cannot be used
    app_version: str
    live_fetching_enabled: bool            # from config; no endpoint fetches during a request regardless
    snapshot: SnapshotSummary | None
    snapshot_error: str | None
    tickers_error: str | None


class ModelTimings(BaseModel):
    total: float | None                    # server-side ms for the whole call, including loading the model
    load: float | None                     # part of total spent loading the model


class ModelTest(BaseModel):
    model: str                             # the model that answered, as the server names it
    parsed: dict                           # the reply as JSON, checked against the schema: {"status": "ok", "note": "..."}
    text: str                              # the raw reply text (any <think> block removed)
    timings_ms: ModelTimings
    tokens_per_second: float | None        # from the server's own counts; None if it did not report them
    prompt_tokens: int | None
    completion_tokens: int | None


class TickerOut(BaseModel):
    ticker: str
    company_name: str
    names: list[str]
    items_in_snapshot: int | None          # None when the snapshot cannot be used
    has_data: bool
