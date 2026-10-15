import dataclasses
import json

import pytest
import requests

from mizan.llm import BadOutput, ChatResult, LLMUnavailable, ModelMissing
from mizan.llm.ollama import OllamaClient
from mizan.llm.schema_check import schema_errors

SCHEMA = {"type": "object", "properties": {"status": {"type": "string", "enum": ["ok"]}, "note": {"type": "string"}},
          "required": ["status", "note"], "additionalProperties": False}
MESSAGES = [{"role": "system", "content": "Reply with JSON only."}, {"role": "user", "content": "Say ok."}]


def reply(content, **extra):
    """A non-streaming /api/chat body, shaped like the one in Ollama's API reference (durations in nanoseconds)."""
    body = {"model": "qwen3:4b-instruct", "created_at": "2026-10-16T09:00:00Z",
            "message": {"role": "assistant", "content": content}, "done": True, "done_reason": "stop",
            "total_duration": 2_500_000_000, "load_duration": 400_000_000, "prompt_eval_count": 31,
            "prompt_eval_duration": 300_000_000, "eval_count": 20, "eval_duration": 1_000_000_000}
    body.update(extra)
    return body


class Resp:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._body


class Session:
    """Serves queued POST answers in order; an Exception value is raised instead. Records every request."""

    def __init__(self, *answers):
        self.answers, self.posts = list(answers), []

    def post(self, url, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def client(*answers, **kwargs):
    return OllamaClient("http://mac:11434/", "qwen3:4b-instruct", Session(*answers), **kwargs)


OK = json.dumps({"status": "ok", "note": "The model is working."})


# --- the interface types -------------------------------------------------------------------

def test_model_missing_tells_how_to_pull_the_model_and_counts_as_unavailable():
    exc = ModelMissing("qwen3:4b-instruct", "http://mac:11434", "model 'qwen3:4b-instruct' not found")
    assert "`ollama pull qwen3:4b-instruct`" in str(exc) and "http://mac:11434" in str(exc) and "not found" in str(exc)
    assert isinstance(exc, LLMUnavailable)                      # a caller that only handles "model unusable" still catches it
    assert not issubclass(BadOutput, LLMUnavailable)            # bad output is a different failure (502, not 503)


def test_chat_result_is_frozen():
    r = ChatResult(text="{}", parsed={}, model="m", prompt_tokens=1, completion_tokens=2, total_ms=3.0, load_ms=0.1,
                   tokens_per_second=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.text = "changed"


# --- the request ---------------------------------------------------------------------------------

def test_request_body_has_think_false_the_schema_the_options_and_keep_alive():
    c = client(Resp(body=reply(OK)), num_ctx=4096, seed=42, num_predict=256, keep_alive="10m")
    c.chat(MESSAGES, SCHEMA)
    (post,) = c.session.posts
    body = post["json"]
    assert post["url"] == "http://mac:11434/api/chat"
    assert body["model"] == "qwen3:4b-instruct" and body["messages"] == MESSAGES
    assert body["stream"] is False and body["think"] is False
    assert body["format"] == SCHEMA
    assert body["options"] == {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 256}
    assert body["keep_alive"] == "10m"


def test_without_a_schema_no_format_is_sent_and_nothing_is_parsed():
    c = client(Resp(body=reply("Hello there.")))
    r = c.chat(MESSAGES)
    assert "format" not in c.session.posts[0]["json"] and r.text == "Hello there." and r.parsed is None


def test_chat_uses_the_long_timeout_and_health_keeps_its_short_one():
    c = client(Resp(body=reply(OK)), timeout_s=3.0, chat_timeout_s=120.0)
    c.chat(MESSAGES, SCHEMA)
    assert c.session.posts[0]["timeout"] == (3.0, 120.0)       # (connect, read): an unreachable server still fails fast
    assert c.timeout_s == 3.0


def test_the_callers_messages_are_not_changed():
    messages = [dict(m) for m in MESSAGES]
    client(Resp(body=reply("nope")), Resp(body=reply(OK))).chat(messages, SCHEMA)
    assert messages == MESSAGES


# --- success ---------------------------------------------------------------------------------------

def test_success_parses_json_and_reads_the_servers_counts_and_timings():
    r = client(Resp(body=reply(OK))).chat(MESSAGES, SCHEMA)
    assert r.parsed == {"status": "ok", "note": "The model is working."} and r.text == OK
    assert r.model == "qwen3:4b-instruct" and r.prompt_tokens == 31 and r.completion_tokens == 20
    assert r.total_ms == 2500.0 and r.load_ms == 400.0
    assert r.tokens_per_second == 20.0                          # 20 tokens in 1 s of eval_duration


def test_missing_timing_fields_give_none_not_a_guess():
    body = reply(OK)
    for key in ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "eval_duration"):
        del body[key]
    r = client(Resp(body=body)).chat(MESSAGES, SCHEMA)
    assert r.parsed["status"] == "ok"
    assert (r.prompt_tokens, r.completion_tokens, r.total_ms, r.load_ms, r.tokens_per_second) == (None,) * 5


def test_zero_eval_duration_gives_no_speed():
    assert client(Resp(body=reply(OK, eval_duration=0))).chat(MESSAGES, SCHEMA).tokens_per_second is None


@pytest.mark.parametrize("content", [
    f"<think>Let me think about the schema.</think>\n{OK}",
    f"<think>\nline one\nline two\n</think>{OK}",
    f"<THINK></THINK>  {OK}  ",
])
def test_think_block_is_stripped_before_parsing(content):
    r = client(Resp(body=reply(content))).chat(MESSAGES, SCHEMA)
    assert r.text == OK and r.parsed["note"] == "The model is working."


def test_think_block_is_stripped_without_a_schema_too():
    assert client(Resp(body=reply("<think>hmm</think>Plain answer."))).chat(MESSAGES).text == "Plain answer."


# --- bad output: one retry, then BadOutput -----------------------------------------------------------

def test_invalid_json_is_retried_once_with_the_problem_shown_to_the_model():
    c = client(Resp(body=reply("Sure! Here you go: ok")), Resp(body=reply(OK)))
    r = c.chat(MESSAGES, SCHEMA)
    assert r.parsed["status"] == "ok" and len(c.session.posts) == 2
    retry_messages = c.session.posts[1]["json"]["messages"]
    assert retry_messages[:2] == MESSAGES
    assert retry_messages[2] == {"role": "assistant", "content": "Sure! Here you go: ok"}
    assert retry_messages[3]["role"] == "user" and "not valid JSON" in retry_messages[3]["content"]
    assert c.session.posts[1]["json"]["format"] == SCHEMA


def test_schema_mismatch_is_retried_then_bad_output():
    wrong = json.dumps({"status": "maybe"})
    c = client(Resp(body=reply(wrong)), Resp(body=reply(wrong)))
    with pytest.raises(BadOutput, match="after 2 attempts") as info:
        c.chat(MESSAGES, SCHEMA)
    assert "'maybe' is not one of" in str(info.value) and "missing required field 'note'" in str(info.value)
    assert len(c.session.posts) == 2                            # exactly one retry


def test_json_that_is_not_an_object_is_bad_output():
    with pytest.raises(BadOutput, match="not an object"):
        client(Resp(body=reply("[1, 2]")), Resp(body=reply('"ok"'))).chat(MESSAGES, SCHEMA)


def test_a_cut_off_reply_says_so():
    cut = reply('{"status": "ok", "no', done_reason="length")
    with pytest.raises(BadOutput, match="cut off at the 512-token limit"):
        client(Resp(body=cut), Resp(body=cut)).chat(MESSAGES, SCHEMA)


def test_without_a_schema_any_text_is_accepted_without_retry():
    c = client(Resp(body=reply("not json at all")))
    assert c.chat(MESSAGES).text == "not json at all" and len(c.session.posts) == 1


# --- server and connection failures ------------------------------------------------------------------

def test_404_means_the_model_is_missing():
    c = client(Resp(status=404, body={"error": "model 'qwen3:4b-instruct' not found"}))
    with pytest.raises(ModelMissing, match=r"ollama pull qwen3:4b-instruct") as info:
        c.chat(MESSAGES, SCHEMA)
    assert "not found" in str(info.value) and len(c.session.posts) == 1          # not retried


def test_404_without_a_json_body_is_still_model_missing():
    with pytest.raises(ModelMissing):
        client(Resp(status=404, bad_json=True)).chat(MESSAGES, SCHEMA)


@pytest.mark.parametrize("exc", [requests.ConnectionError("refused"), requests.ConnectTimeout("no route")])
def test_connection_failure_is_unavailable(exc):
    with pytest.raises(LLMUnavailable, match="not reachable") as info:
        client(exc).chat(MESSAGES, SCHEMA)
    assert not isinstance(info.value, ModelMissing)


def test_slow_reply_is_unavailable_and_names_the_timeout_setting():
    with pytest.raises(LLMUnavailable, match="within 120 s.*MIZAN_OLLAMA_TIMEOUT_S"):
        client(requests.ReadTimeout("slow")).chat(MESSAGES, SCHEMA)


@pytest.mark.parametrize("answer, message", [
    (Resp(status=500, body={"error": "the model failed to generate a response"}), "HTTP 500.*failed to generate"),
    (Resp(status=400, bad_json=True), "HTTP 400"),
    (Resp(bad_json=True), "not JSON"),
    (Resp(body={"done": True}), "no message content"),
    (Resp(body=["unexpected"]), "no message content"),
])
def test_other_server_answers_are_unavailable_not_bad_output(answer, message):
    with pytest.raises(LLMUnavailable, match=message) as info:
        client(answer).chat(MESSAGES, SCHEMA)
    assert not isinstance(info.value, ModelMissing)


def test_a_failure_on_the_retry_is_reported_as_that_failure():
    with pytest.raises(LLMUnavailable, match="not reachable"):
        client(Resp(body=reply("nope")), requests.ConnectionError("gone")).chat(MESSAGES, SCHEMA)


# --- the schema checker ---------------------------------------------------------------------------------

def test_schema_checker_accepts_a_match_and_lists_problems():
    assert schema_errors({"status": "ok", "note": "x"}, SCHEMA) == []
    errors = schema_errors({"status": 1, "extra": True}, SCHEMA)
    assert "$.status: expected string, got int" in errors and "$: unexpected field 'extra'" in errors
    assert "$: missing required field 'note'" in errors


def test_schema_checker_covers_arrays_lengths_and_numbers():
    schema = {"type": "object", "properties": {
        "ids": {"type": "array", "items": {"type": "string", "minLength": 2}, "minItems": 1, "maxItems": 2},
        "score": {"type": "number", "minimum": 0, "maximum": 1}, "flag": {"type": ["boolean", "null"]}}}
    assert schema_errors({"ids": ["ab"], "score": 0.5, "flag": None}, schema) == []
    errors = schema_errors({"ids": ["a", "bb", "cc"], "score": 2, "flag": "yes"}, schema)
    assert any("$.ids[0]: shorter" in e for e in errors) and any("more than 2" in e for e in errors)
    assert any("$.score: above 1" in e for e in errors) and any("$.flag: expected boolean or null" in e for e in errors)
    assert schema_errors(True, {"type": "integer"}) == ["$: expected integer, got bool"]


def test_schema_checker_refuses_keywords_it_cannot_check():
    with pytest.raises(ValueError, match="pattern"):
        schema_errors("x", {"type": "string", "pattern": "^x$"})
    with pytest.raises(ValueError, match="additionalProperties"):
        schema_errors({}, {"type": "object", "additionalProperties": {"type": "string"}})
