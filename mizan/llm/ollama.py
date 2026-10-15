"""Ollama client (health check only for now).

Uses two endpoints documented in Ollama's API reference (checked 2026-10-15):
  GET /api/tags  -> {"models": [{"name", "model", "size", "details": {"parameter_size", "quantization_level", ...}}]}
  GET /api/ps    -> {"models": [{"name", "model", "size_vram", "expires_at", ...}]}  (models loaded in memory)

Not yet exercised against a real Ollama server: the development laptop has none. The tests use a fake HTTP session
shaped like those responses.
"""

import time

import requests

from mizan.llm.base import LLMUnavailable, LoadedModel, ModelHealth


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3:8b",
                 session=None, timeout_s: float = 3.0, clock=time.monotonic):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = session or requests.Session()
        self.timeout_s = timeout_s
        self._clock = clock

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
