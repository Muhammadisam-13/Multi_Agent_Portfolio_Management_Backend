import dataclasses
import json
import socket

import pytest
from starlette.testclient import TestClient

from api.main import create_app
from mizan.llm import BadOutput, LLMUnavailable, ModelMissing
from mizan.llm.fake import FakeLLM, chat_result
from mizan.llm.selftest import SELF_TEST_MESSAGES, SELF_TEST_SCHEMA
from tests.test_api import LOCAL, make_settings

OK = {"status": "ok", "note": "I am working."}


def app_with(tmp_path, fake):
    return TestClient(create_app(make_settings(tmp_path), llm=fake))


# --- success -------------------------------------------------------------------------------------

def test_model_test_returns_the_parsed_reply_with_timings_and_counts(tmp_path):
    fake = FakeLLM(replies=[chat_result(json.dumps(OK), OK, model="qwen3:4b-instruct")])
    r = app_with(tmp_path, fake).post("/model/test")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"model", "parsed", "text", "timings_ms", "tokens_per_second", "prompt_tokens", "completion_tokens"}
    assert body["model"] == "qwen3:4b-instruct" and body["parsed"] == OK and json.loads(body["text"]) == OK
    assert body["timings_ms"] == {"total": 1000.0, "load": 100.0}
    assert body["tokens_per_second"] == 20.0 and body["prompt_tokens"] == 30 and body["completion_tokens"] == 20


def test_model_test_sends_the_fixed_prompt_with_its_schema(tmp_path):
    fake = FakeLLM()
    app_with(tmp_path, fake).post("/model/test")
    assert fake.chat_calls == [(SELF_TEST_MESSAGES, SELF_TEST_SCHEMA)]
    assert SELF_TEST_SCHEMA["required"] == ["status", "note"] and '"status": "ok"' in SELF_TEST_MESSAGES[-1]["content"]


def test_missing_counts_come_back_as_null(tmp_path):
    bare = dataclasses.replace(chat_result(json.dumps(OK), OK), total_ms=None, load_ms=None, tokens_per_second=None,
                               prompt_tokens=None, completion_tokens=None)
    body = app_with(tmp_path, FakeLLM(replies=[bare])).post("/model/test").json()
    assert body["timings_ms"] == {"total": None, "load": None} and body["tokens_per_second"] is None


def test_get_is_not_allowed(tmp_path):
    assert app_with(tmp_path, FakeLLM()).get("/model/test").status_code == 405


# --- errors ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("error, status, text", [
    (LLMUnavailable("Ollama at http://mac:11434 is not reachable (ConnectionError)."), 503, "not reachable"),
    (ModelMissing("qwen3:4b-instruct", "http://mac:11434"), 503, "ollama pull qwen3:4b-instruct"),
    (BadOutput("Model 'qwen3:4b-instruct' did not return JSON matching the schema after 2 attempts."), 502, "after 2 attempts"),
])
def test_model_errors_map_to_status_codes_with_a_readable_detail(tmp_path, error, status, text):
    r = app_with(tmp_path, FakeLLM(chat_error=error)).post("/model/test")
    assert r.status_code == status and set(r.json()) == {"detail"}
    assert isinstance(r.json()["detail"], str) and text in r.json()["detail"]


def test_a_reply_without_parsed_json_is_502(tmp_path):
    r = app_with(tmp_path, FakeLLM(replies=[chat_result("ok", None)])).post("/model/test")
    assert r.status_code == 502 and "no parsed JSON" in r.json()["detail"]


def test_model_test_with_the_real_client_and_nothing_listening(tmp_path):
    """No fake: the real Ollama client against a closed local port must give a clean 503, not a crash."""
    c = TestClient(create_app(make_settings(tmp_path, ollama_url="http://127.0.0.1:9")))
    r = c.post("/model/test")
    assert r.status_code == 503 and "not reachable" in r.json()["detail"]


def test_model_trouble_does_not_break_the_data_endpoints(tmp_path):
    c = app_with(tmp_path, FakeLLM(chat_error=BadOutput("bad")))
    assert c.post("/model/test").status_code == 502
    assert c.get("/health").json()["status"] == "ok" and c.get("/tickers/AAA/bundle?as_of=2025-06-30").status_code == 200


# --- contract and no network --------------------------------------------------------------------------

def test_openapi_lists_model_test_as_a_post(tmp_path):
    paths = app_with(tmp_path, FakeLLM()).get("/openapi.json").json()["paths"]
    assert "post" in paths["/model/test"]


def test_model_test_with_a_fake_model_opens_no_outside_connection(tmp_path, monkeypatch):
    attempts = []
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in LOCAL:
            attempts.append(host)
            raise AssertionError(f"/model/test tried to connect to {host}")
        return real_connect(self, address, *args, **kwargs)

    c = app_with(tmp_path, FakeLLM())
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    assert c.post("/model/test").status_code == 200 and attempts == []
