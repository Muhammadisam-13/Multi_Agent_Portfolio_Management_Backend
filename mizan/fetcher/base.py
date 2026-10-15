"""What every evidence fetcher returns, so fetchers stay swappable."""

from dataclasses import dataclass, field

from mizan.schemas import EvidenceItem


@dataclass
class FetchResult:
    items: list[EvidenceItem]
    warnings: list[str] = field(default_factory=list)
