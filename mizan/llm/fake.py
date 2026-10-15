"""A stand-in model for tests: returns a fixed health report, or raises LLMUnavailable."""

from mizan.llm.base import LLMUnavailable, LoadedModel, ModelHealth


def healthy_report(model: str = "qwen3:8b", loaded: bool = True) -> ModelHealth:
    return ModelHealth(
        reachable=True, url="http://fake-ollama:11434", configured_model=model, model_available=True,
        parameter_size="8.2B", quantization="Q4_K_M", configured_model_loaded=loaded,
        loaded=(LoadedModel(model, 5_800_000_000, "2026-10-15T20:00:00Z"),) if loaded else (), latency_ms=4.2)


class FakeLLM:
    def __init__(self, report: ModelHealth | None = None, unavailable: str | None = None):
        self.report = report or healthy_report()
        self.unavailable = unavailable
        self.calls = 0

    def health(self) -> ModelHealth:
        self.calls += 1
        if self.unavailable:
            raise LLMUnavailable(self.unavailable)
        return self.report
