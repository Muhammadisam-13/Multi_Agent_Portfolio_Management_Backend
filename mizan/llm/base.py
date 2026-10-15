"""LLM interface. Only a health check exists so far (endpoint 6 of docs/api-plan.md); structured calls come with /model/test."""

from dataclasses import dataclass
from typing import Protocol


class LLMUnavailable(Exception):
    """The model server cannot be reached or answered in an unusable way. The message is meant for the UI."""


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


class LLM(Protocol):
    def health(self) -> ModelHealth:
        """Raises LLMUnavailable if the server cannot be reached."""
        ...
