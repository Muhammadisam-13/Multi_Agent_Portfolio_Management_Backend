"""Shared data contract for the retrieval layer.

Change the fields here only with team agreement: the debate agents and the
faithfulness evaluator will both depend on them.
"""

from dataclasses import dataclass
from datetime import date

MACRO = "MACRO"  # ticker value for economy-wide items (SBP policy rate, inflation, ...)


@dataclass(frozen=True)
class EvidenceItem:
    id: str      # stable and unique, so agents can cite it and perturbations can target it
    ticker: str  # PSX symbol, e.g. "OGDC", or MACRO
    source: str  # where it came from, e.g. "psxdata", "sbp_easydata", "psx_announcement"
    type: str    # what it is, e.g. "price", "fundamentals", "announcement", "policy_rate"
    date: date   # date the information became public; used for the no-look-ahead rule
    text: str    # the content shown to the agents

    def __post_init__(self):
        if not self.id:
            raise ValueError("EvidenceItem.id must be non-empty")
        if not self.ticker or self.ticker != self.ticker.upper():
            raise ValueError(f"EvidenceItem.ticker must be non-empty upper case, got {self.ticker!r}")
        # datetime is a subclass of date; reject it so time-of-day never sneaks into comparisons
        if type(self.date) is not date:
            raise TypeError(f"EvidenceItem.date must be datetime.date, got {type(self.date).__name__}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "source": self.source,
            "type": self.type,
            "date": self.date.isoformat(),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceItem":
        return cls(
            id=d["id"],
            ticker=d["ticker"],
            source=d["source"],
            type=d["type"],
            date=date.fromisoformat(d["date"]),
            text=d["text"],
        )


@dataclass(frozen=True)
class EvidenceBundle:
    ticker: str
    as_of: date
    items: tuple[EvidenceItem, ...]
