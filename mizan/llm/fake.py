"""A stand-in model for tests: a fixed health report, scripted chat replies, or a configured error."""

import json

from mizan.llm.base import ChatResult, LLMUnavailable, LoadedModel, ModelHealth

DEFAULT_REPLY = json.dumps({"status": "ok", "note": "Fake model reply."})


def healthy_report(model: str = "qwen3:8b", loaded: bool = True) -> ModelHealth:
    return ModelHealth(
        reachable=True, url="http://fake-ollama:11434", configured_model=model, model_available=True,
        parameter_size="8.2B", quantization="Q4_K_M", configured_model_loaded=loaded,
        loaded=(LoadedModel(model, 5_800_000_000, "2026-10-15T20:00:00Z"),) if loaded else (), latency_ms=4.2)


def chat_result(text: str, parsed: dict | None = None, model: str = "qwen3:8b") -> ChatResult:
    """A reply with fixed, made-up counts and timings (clearly fake: 1 s total, 0.1 s load, 20 tokens/s)."""
    return ChatResult(text=text, parsed=parsed, model=model, prompt_tokens=30, completion_tokens=20,
                      total_ms=1000.0, load_ms=100.0, tokens_per_second=20.0)


class FakeLLM:
    """replies: ChatResult objects, or plain strings (parsed as JSON when a schema is given), returned in order.
    With no replies scripted, every chat call returns DEFAULT_REPLY. chat_error is raised by every chat call.
    `unavailable` makes both health() and chat() raise LLMUnavailable with that message.
    """

    def __init__(self, report: ModelHealth | None = None, unavailable: str | None = None,
                 replies: list[ChatResult | str] | None = None, chat_error: Exception | None = None):
        self.report = report or healthy_report()
        self.unavailable = unavailable
        self.replies = list(replies) if replies is not None else None
        self.chat_error = chat_error
        self.calls = 0                                   # health() calls
        self.chat_calls: list[tuple[list[dict], dict | None]] = []      # (messages, schema) received, in order

    def health(self) -> ModelHealth:
        self.calls += 1
        if self.unavailable:
            raise LLMUnavailable(self.unavailable)
        return self.report

    def chat(self, messages: list[dict], schema: dict | None = None) -> ChatResult:
        self.chat_calls.append(([dict(m) for m in messages], schema))
        if self.unavailable:
            raise LLMUnavailable(self.unavailable)
        if self.chat_error is not None:
            raise self.chat_error
        if self.replies is None:
            reply = DEFAULT_REPLY
        elif self.replies:
            reply = self.replies.pop(0)
        else:
            raise AssertionError("FakeLLM ran out of scripted replies")
        if isinstance(reply, ChatResult):
            return reply
        return chat_result(reply, json.loads(reply) if schema is not None else None, self.report.configured_model)
