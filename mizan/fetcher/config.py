"""Settings for the PSX fetcher.

Live fetching is OFF by default. Tests, demos and evaluation run from the local
cache; pass live=True (CLI: --live) to allow network requests.
"""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FetchConfig:
    live: bool = False                 # master switch: False = never touch the network
    min_interval_s: float = 5.0        # minimum gap between two requests
    timeout_s: float = 30.0
    max_retries: int = 3               # retries after the first attempt (timeouts, 5xx, 429)
    backoff_s: float = 2.0             # waits backoff_s, 2x, 4x ... between retries
    max_age_hours: float = 24.0        # a cached page older than this is refreshed when live
    user_agent: str = "MizanFYP/0.1 (FAST NUCES final year project; low-volume research retrieval)"
    cache_dir: Path = ROOT / "data" / "cache"   # git-ignored; never commit raw PSX pages
