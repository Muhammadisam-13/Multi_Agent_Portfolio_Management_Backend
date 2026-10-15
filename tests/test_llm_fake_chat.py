import pytest

from mizan.llm import BadOutput, LLMUnavailable, ModelMissing
from mizan.llm.fake import DEFAULT_REPLY, FakeLLM, chat_result

MESSAGES = [{"role": "user", "content": "Say ok."}]
SCHEMA = {"type": "object"}


def test_scripted_replies_come_back_in_order():
    first = chat_result("first")
    fake = FakeLLM(replies=[first, '{"status": "ok", "note": "second"}'])
    assert fake.chat(MESSAGES) is first
    second = fake.chat(MESSAGES, SCHEMA)
    assert second.text == '{"status": "ok", "note": "second"}' and second.parsed == {"status": "ok", "note": "second"}
    with pytest.raises(AssertionError, match="ran out"):
        fake.chat(MESSAGES)


def test_a_string_reply_without_a_schema_is_not_parsed():
    assert FakeLLM(replies=['{"a": 1}']).chat(MESSAGES).parsed is None


def test_default_reply_when_nothing_is_scripted():
    fake = FakeLLM()
    assert fake.chat(MESSAGES, SCHEMA).text == DEFAULT_REPLY and fake.chat(MESSAGES, SCHEMA).parsed["status"] == "ok"


def test_records_the_messages_and_schema_it_received():
    fake = FakeLLM()
    fake.chat(MESSAGES, SCHEMA)
    fake.chat([{"role": "user", "content": "again"}])
    assert fake.chat_calls == [(MESSAGES, SCHEMA), ([{"role": "user", "content": "again"}], None)]


@pytest.mark.parametrize("error", [BadOutput("no valid JSON"), ModelMissing("m", "http://x"), LLMUnavailable("down")])
def test_raises_the_configured_error_and_still_records_the_call(error):
    fake = FakeLLM(chat_error=error)
    with pytest.raises(type(error)):
        fake.chat(MESSAGES, SCHEMA)
    assert len(fake.chat_calls) == 1


def test_unavailable_applies_to_chat_too():
    with pytest.raises(LLMUnavailable, match="down"):
        FakeLLM(unavailable="the model server is down").chat(MESSAGES)
