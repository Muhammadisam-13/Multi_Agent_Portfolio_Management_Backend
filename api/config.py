"""API settings, read from environment variables (all optional).

    MIZAN_SNAPSHOT        snapshot name under data/snapshots/ (or a path)       default demo-v3
    MIZAN_SNAPSHOTS_DIR   where snapshots live                                  default <repo>/data/snapshots
    MIZAN_CACHE_DIR       where the price cache lives                           default <repo>/data/cache
    MIZAN_TICKERS_FILE    ticker -> company names                               default <repo>/data/ticker_names.json
    MIZAN_LIVE_FETCH      1/true to ENABLE live fetching in config              default off
    MIZAN_OLLAMA_URL      Ollama base URL                                       default http://localhost:11434
    MIZAN_OLLAMA_MODEL    model name to look for                                default qwen3:8b (tag not verified)
    MIZAN_OLLAMA_NUM_CTX  context window sent with each chat call (tokens)      default 4096
    MIZAN_OLLAMA_TIMEOUT_S  seconds to wait for a chat reply (health uses 3 s)  default 120
    MIZAN_OLLAMA_SEED     sampling seed sent with each chat call                default 42
    MIZAN_OLLAMA_KEEP_ALIVE  how long Ollama keeps the model loaded after a call, as a duration such as 30m or 1h
                                                                                default 30m
    MIZAN_ASK_BUDGET_TOKENS  evidence budget for POST /ask, in estimated tokens  default 2500 (reason in Settings below)
    MIZAN_CORS_ORIGINS    extra browser origins allowed to call the API, comma-separated, e.g.
                          http://192.168.100.20:8080 (http://localhost and http://127.0.0.1 on any port are always allowed)
                                                                                default none

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
    ollama_num_ctx: int = 4096
    ollama_timeout_s: float = 120.0
    ollama_seed: int = 42
    ollama_keep_alive: str = "30m"
    # Evidence budget for POST /ask. With num_ctx 4096 the prompt must also hold the instructions, the question (up to 500
    # characters) and leave room for the answer (num_predict 512): 4096 - 512 = 3584 tokens for the prompt, of which 2500 go to
    # evidence and about 1,000 stay for the rest. select_context counts pessimistically (3 characters per token), so the real
    # evidence is usually smaller than 2500 tokens. This is an estimate, not a tokenizer count: digit-heavy text such as price
    # rows can tokenize worse. Check prompt_tokens in the /ask response on the real model. Raise it with MIZAN_OLLAMA_NUM_CTX.
    ask_budget_tokens: int = 2500
    cors_origins: tuple[str, ...] = ()

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
            ollama_num_ctx=_number(env, "MIZAN_OLLAMA_NUM_CTX", d.ollama_num_ctx, int, positive=True),
            ollama_timeout_s=_number(env, "MIZAN_OLLAMA_TIMEOUT_S", d.ollama_timeout_s, float, positive=True),
            ollama_seed=_number(env, "MIZAN_OLLAMA_SEED", d.ollama_seed, int),
            ollama_keep_alive=env.get("MIZAN_OLLAMA_KEEP_ALIVE", "").strip() or d.ollama_keep_alive,
            ask_budget_tokens=_number(env, "MIZAN_ASK_BUDGET_TOKENS", d.ask_budget_tokens, int, positive=True),
            cors_origins=tuple(o.strip().rstrip("/") for o in env.get("MIZAN_CORS_ORIGINS", "").split(",") if o.strip()),
        )


def _number(env, name: str, default, kind, positive: bool = False):
    """A numeric setting; a bad value stops startup with a message naming the variable."""
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ValueError(f"{name} must be a {'whole ' if kind is int else ''}number, got {raw!r}") from None
    if positive and value <= 0:
        raise ValueError(f"{name} must be greater than 0, got {raw!r}")
    return value
