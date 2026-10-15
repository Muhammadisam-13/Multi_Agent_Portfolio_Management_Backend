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


class TickerOut(BaseModel):
    ticker: str
    company_name: str
    names: list[str]
    items_in_snapshot: int | None          # None when the snapshot cannot be used
    has_data: bool
