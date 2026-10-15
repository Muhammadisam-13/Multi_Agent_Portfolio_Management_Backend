"""One fixed, small structured call that shows the local model returns schema-valid JSON (endpoint 7 of docs/api-plan.md)."""

from mizan.llm.base import LLM, BadOutput, ChatResult

SELF_TEST_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok"]},
        "note": {"type": "string", "minLength": 1, "maxLength": 300},
    },
    "required": ["status", "note"],
    "additionalProperties": False,
}

SELF_TEST_MESSAGES = [
    {"role": "system", "content": "You are a health check for a software system. Reply with JSON only, no other text."},
    {"role": "user", "content": 'Reply with exactly this JSON object: {"status": "ok", "note": "<one short sentence>"}, '
                                'where the note is one short sentence saying that you are working.'},
]


def run_self_test(llm: LLM) -> ChatResult:
    """Raises what llm.chat raises: LLMUnavailable, ModelMissing or BadOutput."""
    result = llm.chat(SELF_TEST_MESSAGES, SELF_TEST_SCHEMA)
    if result.parsed is None:                         # an LLM implementation must parse when given a schema; check anyway
        raise BadOutput(f"Model '{result.model}' returned no parsed JSON for the self-test.")
    return result
