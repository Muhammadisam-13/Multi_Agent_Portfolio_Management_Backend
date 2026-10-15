"""Opt-in test against a real Ollama server. Skipped unless MIZAN_LIVE_OLLAMA=1.

Uses the same settings as the API (MIZAN_OLLAMA_URL, MIZAN_OLLAMA_MODEL, MIZAN_OLLAMA_NUM_CTX, MIZAN_OLLAMA_TIMEOUT_S,
MIZAN_OLLAMA_SEED, MIZAN_OLLAMA_KEEP_ALIVE, MIZAN_ASK_BUDGET_TOKENS, MIZAN_SNAPSHOT).
Run:  $env:MIZAN_LIVE_OLLAMA = "1"; venv\\Scripts\\python.exe -m pytest -m ollama -v -s
The ask test also needs the local snapshot (default demo-v3) with OGDC items.
"""

import os
from datetime import date

import pytest

from api.config import Settings
from mizan.llm.ask import ask
from mizan.llm.ollama import OllamaClient
from mizan.llm.selftest import run_self_test
from mizan.retrieval.store import SnapshotStore, resolve_snapshot_folder

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(os.environ.get("MIZAN_LIVE_OLLAMA") != "1", reason="live Ollama test; set MIZAN_LIVE_OLLAMA=1 to run"),
]


def live_client(s: Settings) -> OllamaClient:
    return OllamaClient(s.ollama_url, s.ollama_model, chat_timeout_s=s.ollama_timeout_s, num_ctx=s.ollama_num_ctx,
                        seed=s.ollama_seed, keep_alive=s.ollama_keep_alive)


def test_real_model_returns_schema_valid_json():
    s = Settings.from_env()
    llm = live_client(s)
    health = llm.health()
    assert health.model_available, f"{s.ollama_model} is not pulled on {s.ollama_url}"
    result = run_self_test(llm)
    print(f"\nmodel={result.model} parsed={result.parsed} total_ms={result.total_ms} load_ms={result.load_ms} "
          f"tokens/s={result.tokens_per_second} prompt_tokens={result.prompt_tokens} completion_tokens={result.completion_tokens}")
    assert result.parsed["status"] == "ok" and result.parsed["note"].strip()


def test_real_model_answers_over_ogdc_evidence():
    s = Settings.from_env()
    as_of = date(2026, 9, 8)
    store = SnapshotStore.load(resolve_snapshot_folder(s.snapshot, s.snapshots_dir))
    result = ask("What did OGDC announce about its annual results?", store.bundle("OGDC", as_of), live_client(s),
                 s.ask_budget_tokens)
    print(f"\nmodel={result.model} attempts={result.attempts} insufficient_evidence={result.insufficient_evidence}"
          f"\nanswer={result.answer}\ncited_ids={list(result.cited_ids)}"
          f"\nclaims={[(c.text, list(c.evidence_ids)) for c in result.claims]}"
          f"\nretrieval_ms={result.timings.retrieval_ms} model_ms={result.timings.model_ms} tokens/s={result.tokens_per_second} "
          f"prompt_tokens={result.prompt_tokens} completion_tokens={result.completion_tokens}"
          f"\nevidence shown={len(result.evidence)} used_tokens={result.context.used_tokens}/{result.context.budget_tokens} "
          f"dropped={result.context.dropped}")
    assert result.evidence and all(i.date <= as_of and i.ticker in ("OGDC", "MACRO") for i in result.evidence)
    assert set(result.cited_ids) <= {i.id for i in result.evidence}
