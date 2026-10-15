import pytest

from api.config import Settings
from api.main import create_app
from mizan.llm.ollama import OllamaClient

OLLAMA_VARS = ("MIZAN_OLLAMA_URL", "MIZAN_OLLAMA_MODEL", "MIZAN_OLLAMA_NUM_CTX", "MIZAN_OLLAMA_TIMEOUT_S", "MIZAN_OLLAMA_SEED",
               "MIZAN_OLLAMA_KEEP_ALIVE", "MIZAN_ASK_BUDGET_TOKENS", "MIZAN_CORS_ORIGINS")


@pytest.fixture
def clean_env(monkeypatch):
    for name in OLLAMA_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_chat_settings_defaults(clean_env):
    s = Settings.from_env()
    assert (s.ollama_num_ctx, s.ollama_timeout_s, s.ollama_seed) == (4096, 120.0, 42)


def test_chat_settings_from_the_environment(clean_env):
    clean_env.setenv("MIZAN_OLLAMA_NUM_CTX", "8192")
    clean_env.setenv("MIZAN_OLLAMA_TIMEOUT_S", "45.5")
    clean_env.setenv("MIZAN_OLLAMA_SEED", "7")
    s = Settings.from_env()
    assert (s.ollama_num_ctx, s.ollama_timeout_s, s.ollama_seed) == (8192, 45.5, 7)


def test_empty_values_fall_back_to_the_defaults(clean_env):
    clean_env.setenv("MIZAN_OLLAMA_NUM_CTX", "  ")
    assert Settings.from_env().ollama_num_ctx == 4096


@pytest.mark.parametrize("name, value, message", [
    ("MIZAN_OLLAMA_NUM_CTX", "lots", "MIZAN_OLLAMA_NUM_CTX must be a whole number"),
    ("MIZAN_OLLAMA_NUM_CTX", "4096.5", "must be a whole number"),
    ("MIZAN_OLLAMA_TIMEOUT_S", "0", "MIZAN_OLLAMA_TIMEOUT_S must be greater than 0"),
    ("MIZAN_OLLAMA_SEED", "x", "MIZAN_OLLAMA_SEED must be a whole number"),
    ("MIZAN_ASK_BUDGET_TOKENS", "0", "MIZAN_ASK_BUDGET_TOKENS must be greater than 0"),
    ("MIZAN_ASK_BUDGET_TOKENS", "2.5k", "MIZAN_ASK_BUDGET_TOKENS must be a whole number"),
])
def test_bad_values_stop_with_a_message_naming_the_variable(clean_env, name, value, message):
    clean_env.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        Settings.from_env()


def test_ask_and_cors_settings_defaults(clean_env):
    s = Settings.from_env()
    assert (s.ollama_keep_alive, s.ask_budget_tokens, s.cors_origins) == ("30m", 2500, ())


def test_ask_and_cors_settings_from_the_environment(clean_env):
    clean_env.setenv("MIZAN_OLLAMA_KEEP_ALIVE", " 1h ")
    clean_env.setenv("MIZAN_ASK_BUDGET_TOKENS", "1800")
    clean_env.setenv("MIZAN_CORS_ORIGINS", "http://192.168.100.20:8080/, ,https://mizan.example")
    s = Settings.from_env()
    assert (s.ollama_keep_alive, s.ask_budget_tokens) == ("1h", 1800)
    assert s.cors_origins == ("http://192.168.100.20:8080", "https://mizan.example")       # trailing slash dropped, blanks ignored


def test_empty_keep_alive_falls_back_to_the_default(clean_env):
    clean_env.setenv("MIZAN_OLLAMA_KEEP_ALIVE", "")
    assert Settings.from_env().ollama_keep_alive == "30m"


def test_the_app_passes_the_settings_to_the_ollama_client(tmp_path):
    settings = Settings(snapshots_dir=tmp_path, ticker_names_path=tmp_path / "none.json", ollama_url="http://mac:11434",
                        ollama_model="qwen3:4b-instruct", ollama_num_ctx=2048, ollama_timeout_s=30.0, ollama_seed=9,
                        ollama_keep_alive="45m")
    llm = create_app(settings).state.llm                        # building the client makes no request
    assert isinstance(llm, OllamaClient)
    assert (llm.base_url, llm.model, llm.num_ctx, llm.chat_timeout_s, llm.seed) == ("http://mac:11434", "qwen3:4b-instruct", 2048, 30.0, 9)
    assert llm.keep_alive == "45m" and llm._chat_body([], None)["keep_alive"] == "45m"
    assert llm.timeout_s == 3.0                                  # the health check keeps its short timeout
