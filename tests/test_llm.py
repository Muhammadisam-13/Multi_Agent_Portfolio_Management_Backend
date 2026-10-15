import pytest
import requests

from mizan.llm import LLMUnavailable
from mizan.llm.fake import FakeLLM, healthy_report
from mizan.llm.ollama import OllamaClient

# shaped like the responses in Ollama's API reference
TAGS = {"models": [
    {"name": "qwen3:8b", "model": "qwen3:8b", "size": 5_200_000_000,
     "details": {"parameter_size": "8.2B", "quantization_level": "Q4_K_M", "family": "qwen3"}},
    {"name": "llama3.2:latest", "model": "llama3.2:latest", "details": {"parameter_size": "3.2B", "quantization_level": "Q4_K_M"}},
]}
PS = {"models": [{"name": "qwen3:8b", "model": "qwen3:8b", "size_vram": 5_800_000_000, "expires_at": "2026-10-15T20:00:00Z"}]}


class Resp:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._body


class Session:
    """Serves queued answers by path; an Exception value is raised instead."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, timeout):
        self.calls.append((url, timeout))
        answer = self.answers[url.rsplit("/api/", 1)[1]]
        if isinstance(answer, Exception):
            raise answer
        return answer


def client(answers, **kwargs):
    ticks = iter([10.0, 10.0042])                       # a fake clock: 4.2 ms between the two readings
    return OllamaClient("http://gpu-box:11434/", "qwen3:8b", Session(answers), clock=lambda: next(ticks), **kwargs)


def test_healthy_server_reports_model_quantization_vram_and_latency():
    h = client({"tags": Resp(body=TAGS), "ps": Resp(body=PS)}).health()
    assert h.reachable and h.url == "http://gpu-box:11434"                       # trailing slash removed
    assert h.model_available and h.parameter_size == "8.2B" and h.quantization == "Q4_K_M"
    assert h.configured_model_loaded and h.loaded[0].size_vram_bytes == 5_800_000_000
    assert h.latency_ms == pytest.approx(4.2, abs=0.1)


def test_model_pulled_but_not_loaded():
    h = client({"tags": Resp(body=TAGS), "ps": Resp(body={"models": []})}).health()
    assert h.model_available and not h.configured_model_loaded and h.loaded == ()


def test_model_not_pulled_is_reported_not_raised():
    c = OllamaClient("http://x", "qwen3:8b", Session({"tags": Resp(body={"models": []}), "ps": Resp(body={"models": []})}))
    h = c.health()
    assert h.reachable and not h.model_available and h.quantization is None


def test_latest_tag_is_matched():
    c = OllamaClient("http://x", "llama3.2", Session({"tags": Resp(body=TAGS), "ps": Resp(body={"models": []})}))
    assert c.health().model_available


def test_unreachable_server_raises_with_a_readable_message():
    with pytest.raises(LLMUnavailable, match="not reachable"):
        client({"tags": requests.ConnectionError("refused")}).health()
    with pytest.raises(LLMUnavailable, match="not reachable"):
        client({"tags": requests.Timeout("slow")}).health()


@pytest.mark.parametrize("answer, message", [
    (Resp(status=500), "HTTP 500"),
    (Resp(bad_json=True), "not JSON"),
    (Resp(body=["unexpected"]), "unexpected answer"),
])
def test_bad_answers_to_the_model_list_raise(answer, message):
    with pytest.raises(LLMUnavailable, match=message):
        client({"tags": answer}).health()


def test_missing_ps_endpoint_is_tolerated():
    for ps in (Resp(status=404), requests.ConnectionError("x"), Resp(bad_json=True)):
        h = client({"tags": Resp(body=TAGS), "ps": ps}).health()
        assert h.model_available and h.loaded == () and not h.configured_model_loaded


def test_requests_use_the_timeout():
    c = client({"tags": Resp(body=TAGS), "ps": Resp(body=PS)}, timeout_s=1.5)
    c.health()
    assert all(t == 1.5 for _, t in c.session.calls) and len(c.session.calls) == 2


def test_fake_model():
    assert FakeLLM().health().quantization == "Q4_K_M" and healthy_report(loaded=False).loaded == ()
    with pytest.raises(LLMUnavailable, match="down"):
        FakeLLM(unavailable="the model server is down").health()
