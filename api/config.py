"""API settings, read from environment variables (all optional).

    MIZAN_SNAPSHOT        snapshot name under data/snapshots/ (or a path)       default demo-v3
    MIZAN_SNAPSHOTS_DIR   where snapshots live                                  default <repo>/data/snapshots
    MIZAN_CACHE_DIR       where the price cache lives                           default <repo>/data/cache
    MIZAN_TICKERS_FILE    ticker -> company names                               default <repo>/data/ticker_names.json
    MIZAN_LIVE_FETCH      1/true to ENABLE live fetching in config              default off
    MIZAN_OLLAMA_URL      Ollama base URL                                       default http://localhost:11434
    MIZAN_OLLAMA_MODEL    model name to look for                                default qwen3:8b (tag not verified)

MIZAN_LIVE_FETCH is only reported by /health. No endpoint fetches from PSX during a request: every loader the API builds is
constructed with live fetching off, whatever this flag says (decision D11).
"""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    snapshot: str = "demo-v3"
    snapshots_dir: Path = ROOT / "data" / "snapshots"
    cache_dir: Path = ROOT / "data" / "cache"
    ticker_names_path: Path = ROOT / "data" / "ticker_names.json"
    live_fetching_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        d = cls()
        return cls(
            snapshot=env.get("MIZAN_SNAPSHOT", d.snapshot),
            snapshots_dir=Path(env.get("MIZAN_SNAPSHOTS_DIR", d.snapshots_dir)),
            cache_dir=Path(env.get("MIZAN_CACHE_DIR", d.cache_dir)),
            ticker_names_path=Path(env.get("MIZAN_TICKERS_FILE", d.ticker_names_path)),
            live_fetching_enabled=env.get("MIZAN_LIVE_FETCH", "").strip().lower() in {"1", "true", "yes", "on"},
            ollama_url=env.get("MIZAN_OLLAMA_URL", d.ollama_url),
            ollama_model=env.get("MIZAN_OLLAMA_MODEL", d.ollama_model),
        )
