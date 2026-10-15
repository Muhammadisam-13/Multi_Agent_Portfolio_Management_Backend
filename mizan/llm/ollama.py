"""Ollama client: a health check and one chat call with optional JSON-schema output.

Uses three endpoints documented in Ollama's API reference (checked 2026-10-15 and, for /api/chat, 2026-10-16 at
docs.ollama.com/api/chat and docs.ollama.com/api/errors):
  GET  /api/tags  -> {"models": [{"name", "model", "size", "details": {"parameter_size", "quantization_level", ...}}]}
  GET  /api/ps    -> {"models": [{"name", "model", "size_vram", "expires_at", ...}]}  (models loaded in memory)
  POST /api/chat  <- {"model", "messages", "stream", "think", "format", "options": {"temperature", "seed", "num_ctx",
                      "num_predict"}, "keep_alive"}
                  -> {"model", "message": {"role", "content", "thinking"?}, "done", "done_reason", "total_duration",
                      "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration"}
                     (durations in nanoseconds); errors are {"error": "..."}, with 404 when the model does not exist.

The health check has been run once against a real Ollama (decision D12). The chat call has not: it is tested with a fake
HTTP session shaped like the responses above.
"""

import json
import logging
import re
import time

import requests

from mizan.llm.base import BadOutput, ChatResult, LLMUnavailable, LoadedModel, ModelHealth, ModelMissing
from mizan.llm.schema_check import schema_errors

# docs.ollama.com/api/errors lists "404: Not Found (model doesn't exist, etc.)". The exact error text is not documented,
# so a missing model is recognised by this status alone and the server's own text is passed on in the message.
MODEL_MISSING_STATUS = 404

log = logging.getLogger(__name__)

THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

# Sent after a reply that is not schema-valid JSON. The options are deterministic (temperature 0, fixed seed), so repeating
# the same request would most likely repeat the same reply; naming the problem changes the prompt. The bad reply itself is not
# sent back: it can be as long as num_predict, and the prompt, that reply and a new reply of up to num_predict tokens would not
# fit together in a 4096-token context (decision D13, 2026-10-16).
RETRY_PROMPT = ("Your previous reply could not be used: {problem}. Reply again with only a JSON object that matches the "
                "requested schema, and nothing else.")
SHORTER = " Keep it short: the whole reply must fit in {num_predict} tokens."
LOG_TAIL_CHARS = 200            # how much of an unusable reply goes to the server log (never to the API error)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3:8b",
                 session=None, timeout_s: float = 3.0, clock=time.monotonic, *,
                 chat_timeout_s: float = 120.0, num_ctx: int = 4096, num_predict: int = 1024, seed: int = 42,
                 keep_alive: str = "10m"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = session or requests.Session()
        self.timeout_s = timeout_s                  # health requests, and connecting for a chat
        self.chat_timeout_s = chat_timeout_s        # waiting for a chat reply (loading the model and generating)
        self.num_ctx = num_ctx
        self.num_predict = num_predict              # cap on generated tokens
        self.seed = seed
        self.keep_alive = keep_alive                # how long the server keeps the model loaded after the call
        self._clock = clock

    # --- health ---------------------------------------------------------------------------
    def health(self) -> ModelHealth:
        started = self._clock()
        tags = self._get_json("/api/tags", required=True)
        latency_ms = (self._clock() - started) * 1000
        available = {m.get("name") or m.get("model"): m for m in tags.get("models", [])}
        entry = available.get(self.model) or available.get(f"{self.model}:latest")

        loaded: tuple[LoadedModel, ...] = ()
        ps = self._get_json("/api/ps", required=False)       # missing on old servers: then nothing is reported as loaded
        if ps is not None:
            loaded = tuple(LoadedModel(name=m.get("name") or m.get("model") or "?", size_vram_bytes=m.get("size_vram"),
                                       expires_at=m.get("expires_at")) for m in ps.get("models", []))
        details = (entry or {}).get("details") or {}
        return ModelHealth(
            reachable=True,
            url=self.base_url,
            configured_model=self.model,
            model_available=entry is not None,
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            configured_model_loaded=any(m.name in (self.model, f"{self.model}:latest") for m in loaded),
            loaded=loaded,
            latency_ms=round(latency_ms, 1),
        )

    # --- chat -----------------------------------------------------------------------------
    def chat(self, messages: list[dict], schema: dict | None = None) -> ChatResult:
        """One non-streaming chat call. With a schema: one retry if the reply is not schema-valid JSON, then BadOutput."""
        messages = [dict(m) for m in messages]
        data = self._post_chat(messages, schema)
        result, problem = self._read_reply(data, schema)
        if problem is None:
            return result
        _log_unusable(self.model, 1, problem, data)
        note = RETRY_PROMPT.format(problem=problem) + (SHORTER.format(num_predict=self.num_predict) if _cut_off(data) else "")
        data = self._post_chat([*messages, {"role": "user", "content": note}], schema)
        result, problem = self._read_reply(data, schema)
        if problem is None:
            return result
        _log_unusable(self.model, 2, problem, data)
        raise BadOutput(f"Model '{self.model}' did not return JSON matching the schema after 2 attempts (last problem: {problem}).")

    def _chat_body(self, messages: list[dict], schema: dict | None) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "seed": self.seed, "num_ctx": self.num_ctx, "num_predict": self.num_predict},
            "keep_alive": self.keep_alive,
        }
        if schema is not None:
            body["format"] = schema
        return body

    def _post_chat(self, messages: list[dict], schema: dict | None) -> dict:
        try:
            resp = self.session.post(f"{self.base_url}/api/chat", json=self._chat_body(messages, schema),
                                     timeout=(self.timeout_s, self.chat_timeout_s))
        except requests.ConnectionError as exc:                   # includes a connect timeout
            raise LLMUnavailable(f"Ollama at {self.base_url} is not reachable ({type(exc).__name__}). "
                                 f"Is it running, and is OLLAMA_HOST open to this machine?") from exc
        except requests.Timeout as exc:
            raise LLMUnavailable(f"Ollama at {self.base_url} did not finish answering within {self.chat_timeout_s:g} s "
                                 f"(MIZAN_OLLAMA_TIMEOUT_S). The model may still be loading; retry, or raise the timeout.") from exc
        except requests.RequestException as exc:
            raise LLMUnavailable(f"Ollama at {self.base_url} could not be asked ({type(exc).__name__}).") from exc

        if resp.status_code == MODEL_MISSING_STATUS:
            raise ModelMissing(self.model, self.base_url, _server_error(resp))
        if resp.status_code != 200:
            said = _server_error(resp)
            raise LLMUnavailable(f"Ollama at {self.base_url} answered HTTP {resp.status_code} for /api/chat"
                                 + (f": {said}." if said else "."))
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMUnavailable(f"Ollama at {self.base_url} sent something that is not JSON for /api/chat.") from exc
        if not isinstance(data, dict) or not isinstance((data.get("message") or {}).get("content"), str):
            raise LLMUnavailable(f"Ollama at {self.base_url} sent an unexpected answer for /api/chat (no message content).")
        return data

    def _read_reply(self, data: dict, schema: dict | None) -> tuple[ChatResult, str | None]:
        """The result, and what is wrong with it when a schema was asked for (None if nothing is)."""
        text = THINK_BLOCK.sub("", data["message"]["content"]).strip()
        parsed, problem = None, None
        if schema is not None:
            parsed, problem = _parse_against(text, schema)
            if problem and _cut_off(data):
                problem += f" (the reply was cut off at the {self.num_predict}-token limit)"
        return ChatResult(
            text=text,
            parsed=parsed if problem is None else None,
            model=data.get("model") or self.model,
            prompt_tokens=_int_or_none(data.get("prompt_eval_count")),
            completion_tokens=_int_or_none(data.get("eval_count")),
            total_ms=_ns_to_ms(data.get("total_duration")),
            load_ms=_ns_to_ms(data.get("load_duration")),
            tokens_per_second=_tokens_per_second(data.get("eval_count"), data.get("eval_duration")),
        ), problem

    # --- shared ---------------------------------------------------------------------------
    def _get_json(self, path: str, required: bool) -> dict | None:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, timeout=self.timeout_s)
        except requests.RequestException as exc:
            if required:
                raise LLMUnavailable(f"Ollama at {self.base_url} is not reachable ({type(exc).__name__}). "
                                     f"Is it running, and is OLLAMA_HOST open to this machine?") from exc
            return None
        if resp.status_code != 200:
            if required:
                raise LLMUnavailable(f"Ollama at {self.base_url} answered HTTP {resp.status_code} for {path}.")
            return None
        try:
            data = resp.json()
        except ValueError as exc:
            if required:
                raise LLMUnavailable(f"Ollama at {self.base_url} sent something that is not JSON for {path}.") from exc
            return None
        if not isinstance(data, dict):
            if required:
                raise LLMUnavailable(f"Ollama at {self.base_url} sent an unexpected answer for {path}.")
            return None
        return data


def _cut_off(data: dict) -> bool:
    return data.get("done_reason") == "length"


def _log_unusable(model: str, attempt: int, problem: str, data: dict) -> None:
    """The end of the raw reply goes to the server log only: it is model output, not a message for the UI."""
    content = data["message"]["content"]
    log.warning("Model '%s' reply %d of 2 is unusable: %s. done_reason=%s, %d characters, last %d: %r", model, attempt, problem,
                data.get("done_reason"), len(content), LOG_TAIL_CHARS, content[-LOG_TAIL_CHARS:])


def _parse_against(text: str, schema: dict) -> tuple[dict | None, str | None]:
    try:
        value = json.loads(text)
    except ValueError:
        return None, "the reply is not valid JSON"
    if not isinstance(value, dict):
        return None, "the reply is JSON but not an object"
    errors = schema_errors(value, schema)
    if errors:
        return None, "the JSON does not match the schema: " + "; ".join(errors[:3])
    return value, None


def _server_error(resp) -> str | None:
    try:
        body = resp.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), str) else None


def _int_or_none(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _ns_to_ms(value) -> float | None:
    return round(value / 1e6, 1) if _int_or_none(value) is not None else None


def _tokens_per_second(eval_count, eval_duration_ns) -> float | None:
    count, duration = _int_or_none(eval_count), _int_or_none(eval_duration_ns)
    if count is None or not duration or duration <= 0:
        return None
    return round(count / (duration / 1e9), 1)
