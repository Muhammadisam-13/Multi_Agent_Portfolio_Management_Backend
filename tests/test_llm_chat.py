import dataclasses

import pytest

from mizan.llm import BadOutput, ChatResult, LLMUnavailable, ModelMissing


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
