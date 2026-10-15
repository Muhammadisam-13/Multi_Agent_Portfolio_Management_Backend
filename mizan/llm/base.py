"""LLM interface: a health check (endpoint 6 of docs/api-plan.md) and one chat call with optional JSON-schema output (endpoint 7)."""

from dataclasses import dataclass
from typing import Protocol


class LLMUnavailable(Exception):
    """The model server cannot be reached or answered in an unusable way. The message is meant for the UI."""


class ModelMissing(LLMUnavailable):
    """The server is up but the configured model has not been pulled. The message names the `ollama pull` command."""

    def __init__(self, model: str, url: str, server_said: str | None = None):
        said = f" (the server said: {server_said})" if server_said else ""
        super().__init__(f"Model '{model}' is not available on the Ollama server at {url}{said}. "
                         f"Run `ollama pull {model}` on that machine, then retry.")
        self.model = model


class BadOutput(Exception):
    """The model answered, but not with JSON that matches the requested schema, even after a retry. The message is meant for the UI."""


@dataclass(frozen=True)
class LoadedModel:
    name: str
    size_vram_bytes: int | None     # memory the model currently holds on the GPU, as reported by the server
    expires_at: str | None          # when the server will unload it if idle


@dataclass(frozen=True)
class ModelHealth:
    reachable: bool                 # always True when returned; unreachable raises LLMUnavailable
    url: str
    configured_model: str
    model_available: bool           # the configured model has been pulled on the server
    parameter_size: str | None      # e.g. "8.2B", from the server's model details
    quantization: str | None        # e.g. "Q4_K_M"; the plan asks to check this
    configured_model_loaded: bool   # currently in memory (so the next call is fast)
    loaded: tuple[LoadedModel, ...]
    latency_ms: float               # round trip of the model-list request, not of a generation


@dataclass(frozen=True)
class ChatResult:
    text: str                       # the reply, with any <think>...</think> block removed
    parsed: dict | None             # the reply as JSON when a schema was given (already checked against it); else None
    model: str                      # the model that answered, as the server names it
    prompt_tokens: int | None       # as reported by the server; None if it did not say
    completion_tokens: int | None
    total_ms: float | None          # server-side time for the whole call, including loading the model
    load_ms: float | None           # part of total_ms spent loading the model (near 0 when it was already in memory)
    tokens_per_second: float | None # generation speed from the server's own counts; None if they are missing


class LLM(Protocol):
    def health(self) -> ModelHealth:
        """Raises LLMUnavailable if the server cannot be reached."""
        ...

    def chat(self, messages: list[dict], schema: dict | None = None) -> ChatResult:
        """messages: [{"role": "system" | "user" | "assistant", "content": str}, ...].

        With a schema, the reply must be a JSON object matching it. Raises LLMUnavailable (server unreachable or failing),
        ModelMissing (model not pulled) or BadOutput (no schema-valid reply after one retry).
        """
        ...
