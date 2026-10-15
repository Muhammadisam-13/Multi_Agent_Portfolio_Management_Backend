"""Response shapes that are specific to the API (the evidence types come from mizan/schemas.py)."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from mizan.schemas import EvidenceItem


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


class AskIn(BaseModel):
    ticker: str = Field(description="PSX symbol, e.g. OGDC (case does not matter).")
    as_of: date | None = Field(None, description="YYYY-MM-DD. Evidence dated after it is never shown to the model. "
                                                 "Default: the newest date in the snapshot.")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] = Field(
        description="1 to 500 characters.")


class ClaimOut(BaseModel):
    text: str
    evidence_ids: list[str]                # every id is one of the items in `evidence`


class AskTimings(BaseModel):
    retrieval: float                       # ms: building the bundle and choosing the context
    model: float                           # ms: wall-clock time of the model call(s), including a retry


class AskContext(BaseModel):
    budget_tokens: int                     # MIZAN_ASK_BUDGET_TOKENS
    used_tokens: int                       # estimated tokens of the evidence shown (3 characters per token)
    dropped: dict[str, int]                # item type -> items of the bundle left out to stay within the budget


class AskOut(BaseModel):
    ticker: str
    as_of: date                            # the date actually used (the default when none was given)
    answer: str
    claims: list[ClaimOut]
    evidence: list[EvidenceItem]           # exactly the items shown to the model
    cited_ids: list[str]                   # every id cited by a claim, in order of first citation
    insufficient_evidence: bool            # the model said the evidence is not enough to answer
    model: str
    timings_ms: AskTimings
    tokens_per_second: float | None        # from the server's own counts for the accepted reply; None if not reported
    prompt_tokens: int | None
    completion_tokens: int | None
    context: AskContext
    attempts: int                          # 2 when the first answer was rejected and the corrective retry was accepted


class TickerOut(BaseModel):
    ticker: str
    company_name: str
    names: list[str]
    items_in_snapshot: int | None          # None when the snapshot cannot be used
    has_data: bool
