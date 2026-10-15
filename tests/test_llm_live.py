"""Opt-in test against a real Ollama server. Skipped unless MIZAN_LIVE_OLLAMA=1.

Uses the same settings as the API (MIZAN_OLLAMA_URL, MIZAN_OLLAMA_MODEL, MIZAN_OLLAMA_NUM_CTX, MIZAN_OLLAMA_TIMEOUT_S,
MIZAN_OLLAMA_SEED). Run:  $env:MIZAN_LIVE_OLLAMA = "1"; venv\\Scripts\\python.exe -m pytest -m ollama -v -s
"""

import os

import pytest

from api.config import Settings
from mizan.llm.ollama import OllamaClient
from mizan.llm.selftest import run_self_test

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(os.environ.get("MIZAN_LIVE_OLLAMA") != "1", reason="live Ollama test; set MIZAN_LIVE_OLLAMA=1 to run"),
]


def test_real_model_returns_schema_valid_json():
    s = Settings.from_env()
    llm = OllamaClient(s.ollama_url, s.ollama_model, chat_timeout_s=s.ollama_timeout_s, num_ctx=s.ollama_num_ctx, seed=s.ollama_seed)
    health = llm.health()
    assert health.model_available, f"{s.ollama_model} is not pulled on {s.ollama_url}"
    result = run_self_test(llm)
    print(f"\nmodel={result.model} parsed={result.parsed} total_ms={result.total_ms} load_ms={result.load_ms} "
          f"tokens/s={result.tokens_per_second} prompt_tokens={result.prompt_tokens} completion_tokens={result.completion_tokens}")
    assert result.parsed["status"] == "ok" and result.parsed["note"].strip()
