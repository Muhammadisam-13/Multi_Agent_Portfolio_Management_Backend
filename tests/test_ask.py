import json
from datetime import date, timedelta
from itertools import count

import pytest

from mizan.llm import BadOutput, LLMUnavailable
from mizan.llm.ask import ANSWER_SCHEMA, NO_EVIDENCE, SYSTEM_PROMPT, UngroundedAnswer, ask, build_messages
from mizan.llm.fake import FakeLLM, chat_result
from mizan.llm.schema_check import schema_errors
from mizan.retrieval.bundle import build_bundle
from mizan.retrieval.context import item_cost
from mizan.schemas import EvidenceItem

AS_OF = date(2026, 9, 8)
QUESTION = "What did AAA announce about its annual results?"
FUTURE_MARKER = "QZX-FUTURE-7731"                  # appears only in an item dated after AS_OF
OTHER_MARKER = "QZX-OTHER-TICKER-4410"             # appears only in another ticker's item

RES = EvidenceItem("AAA-RES-2026-08-20", "AAA", "psx_results", "financial_results", date(2026, 8, 20),
                   "AAA annual results for the year ended June 2026: profit after tax 12.5 billion PKR, final dividend 4.00 PKR per share.")
ANN = EvidenceItem("AAA-ANN-2026-09-01", "AAA", "psx_announcement", "announcement", date(2026, 9, 1),
                   "AAA board meeting held on 1 September 2026 approved the annual results.")
PRICE = EvidenceItem("AAA-PRICE-2026-09-05", "AAA", "psxdata", "price", date(2026, 9, 5), "AAA closed at 210.00 PKR.")
CPI = EvidenceItem("MACRO-CPI-2026-09-02", "MACRO", "sbp", "inflation", date(2026, 9, 2), "CPI inflation for August was 4.1% year on year.")
FUTURE = EvidenceItem("AAA-ANN-2026-10-01", "AAA", "psx_announcement", "announcement", date(2026, 10, 1),
                      f"{FUTURE_MARKER} AAA annual results restated with a large loss.")
OTHER = EvidenceItem("BBB-ANN-2026-09-03", "BBB", "psx_announcement", "announcement", date(2026, 9, 3),
                     f"{OTHER_MARKER} BBB annual results: record profit.")
ALL = [RES, ANN, PRICE, CPI, FUTURE, OTHER]


def reply(answer="AAA reported a profit after tax of 12.5 billion PKR and a final dividend of 4.00 PKR per share.",
          claims=(("Profit after tax was 12.5 billion PKR.", ["AAA-RES-2026-08-20"]),), insufficient=False) -> str:
    return json.dumps({"answer": answer, "claims": [{"text": t, "evidence_ids": list(ids)} for t, ids in claims],
                       "insufficient_evidence": insufficient})


@pytest.fixture
def bundle():
    return build_bundle(ALL, "AAA", AS_OF)


def all_text(fake: FakeLLM) -> str:
    return "\n".join(m["content"] for messages, _ in fake.chat_calls for m in messages)


# --- grounded answers -------------------------------------------------------------------------------

def test_a_grounded_answer_returns_its_evidence_and_cited_ids(bundle):
    fake = FakeLLM(replies=[reply()])
    result = ask(QUESTION, bundle, fake, 2500)
    assert result.answer.startswith("AAA reported") and not result.insufficient_evidence and result.attempts == 1
    assert result.cited_ids == ("AAA-RES-2026-08-20",)
    assert result.claims[0].text == "Profit after tax was 12.5 billion PKR." and result.claims[0].evidence_ids == ("AAA-RES-2026-08-20",)
    assert {i.id for i in result.evidence} == {"AAA-RES-2026-08-20", "AAA-ANN-2026-09-01", "AAA-PRICE-2026-09-05", "MACRO-CPI-2026-09-02"}
    assert set(result.cited_ids) <= {i.id for i in result.evidence}
    assert (result.model, result.tokens_per_second, result.prompt_tokens, result.completion_tokens) == ("qwen3:8b", 20.0, 30, 20)
    assert result.context.budget_tokens == 2500 and result.context.used_tokens <= 2500 and result.context.dropped == {}


def test_the_prompt_is_rules_then_evidence_then_question_with_the_answer_schema(bundle):
    fake = FakeLLM(replies=[reply()])
    ask(QUESTION, bundle, fake, 2500)
    [(messages, schema)] = fake.chat_calls
    assert schema is ANSWER_SCHEMA
    assert [m["role"] for m in messages] == ["system", "user", "user"] and messages[0]["content"] == SYSTEM_PROMPT
    assert "[AAA-RES-2026-08-20] 2026-08-20 | financial_results | psx_results\nAAA annual results" in messages[1]["content"]
    assert messages[1]["content"].startswith("Evidence (4 items):") and messages[2]["content"] == f"Question: {QUESTION}"
    for rule in ("only from the listed evidence", "cite the id", "no outside knowledge", "not enough", "any number",
                 "copied exactly as shown", "Cite only ids from the listed evidence", "at most 2 sentences", "at most 3 claims"):
        assert rule in SYSTEM_PROMPT


def test_ids_with_spaces_brackets_or_repeats_are_cleaned(bundle):
    claims = (("Results were approved.", [" [AAA-ANN-2026-09-01] ", "AAA-ANN-2026-09-01", "AAA-RES-2026-08-20"]),)
    result = ask(QUESTION, bundle, FakeLLM(replies=[reply(claims=claims)]), 2500)
    assert result.claims[0].evidence_ids == ("AAA-ANN-2026-09-01", "AAA-RES-2026-08-20") and result.attempts == 1


def test_the_answer_schema_uses_only_keywords_schema_check_supports():
    assert schema_errors(json.loads(reply()), ANSWER_SCHEMA) == []                  # would raise ValueError otherwise
    assert schema_errors({"answer": "x", "claims": [{"text": "y"}]}, ANSWER_SCHEMA) != []


def test_timings_are_measured_with_the_clock(bundle):
    ticks = count()
    result = ask(QUESTION, bundle, FakeLLM(replies=[reply()]), 2500, clock=lambda: next(ticks) * 0.01)
    assert (result.timings.retrieval_ms, result.timings.model_ms) == (10.0, 10.0)


# --- rejected answers ------------------------------------------------------------------------------

def test_an_unknown_cited_id_gets_one_corrective_retry_then_succeeds(bundle):
    bad = reply(claims=(("Profit rose.", ["AAA-RES-2026-08-20", "AAA-MADE-UP-1"]),))
    fake = FakeLLM(replies=[bad, reply()])
    result = ask(QUESTION, bundle, fake, 2500)
    assert result.attempts == 2 and result.cited_ids == ("AAA-RES-2026-08-20",) and len(fake.chat_calls) == 2
    retry, schema = fake.chat_calls[1]
    assert schema is ANSWER_SCHEMA and retry[:3] == fake.chat_calls[0][0] and len(retry) == 4
    assert retry[3]["role"] == "user" and "AAA-MADE-UP-1" in retry[3]["content"] and "were not listed" in retry[3]["content"]
    assert "square brackets" in retry[3]["content"]
    # Neither the rejected answer nor a list of allowed ids is resent, so the retry fits the context like the first prompt.
    assert "Profit rose." not in retry[3]["content"] and "AAA-RES-2026-08-20" not in retry[3]["content"]


def test_a_rejected_answer_logs_its_tail_but_the_error_does_not_carry_it(bundle, caplog):
    first = reply(claims=(("Profit rose. LOG-MARKER", ["AAA-MADE-UP-1"]),))
    with caplog.at_level("WARNING", logger="mizan.llm.ask"), pytest.raises(UngroundedAnswer) as exc:
        ask(QUESTION, bundle, FakeLLM(replies=[first, first]), 2500)
    logged = [r.getMessage() for r in caplog.records]
    assert len(logged) == 2 and all("LOG-MARKER" in m and "AAA-MADE-UP-1" in m for m in logged)
    assert "LOG-MARKER" not in str(exc.value)


def test_two_ungrounded_answers_raise_with_the_rejected_ids(bundle):
    first = reply(claims=(("Profit rose.", ["AAA-MADE-UP-1"]),))
    second = reply(claims=(("Profit rose.", ["AAA-MADE-UP-2", "AAA-RES-2026-08-20"]),))
    with pytest.raises(UngroundedAnswer) as exc:
        ask(QUESTION, bundle, FakeLLM(replies=[first, second]), 2500)
    assert exc.value.rejected_ids == ("AAA-MADE-UP-2",)
    assert "AAA-MADE-UP-2" in str(exc.value) and "after 2 attempts" in str(exc.value)


@pytest.mark.parametrize("bad, problem", [
    (reply(claims=()), "no claims"),
    (reply(claims=(("Profit rose.", []),)), "claim 1 cites no evidence id"),
    (reply(claims=(("Profit rose.", ["  ", "[]"]),)), "claim 1 cites no evidence id"),
])
def test_an_answer_without_citations_is_retried_then_rejected(bundle, bad, problem):
    fake = FakeLLM(replies=[bad, bad])
    with pytest.raises(UngroundedAnswer, match=problem) as exc:
        ask(QUESTION, bundle, fake, 2500)
    assert exc.value.rejected_ids == () and len(fake.chat_calls) == 2 and problem in fake.chat_calls[1][0][-1]["content"]


def test_a_reply_that_breaks_the_schema_is_bad_output(bundle):
    with pytest.raises(BadOutput, match="does not match the answer schema"):
        ask(QUESTION, bundle, FakeLLM(replies=['{"status": "ok"}']), 2500)
    with pytest.raises(BadOutput, match="no parsed JSON"):
        ask(QUESTION, bundle, FakeLLM(replies=[chat_result("not json", None)]), 2500)


def test_model_errors_pass_through(bundle):
    with pytest.raises(LLMUnavailable, match="down"):
        ask(QUESTION, bundle, FakeLLM(unavailable="the model server is down"), 2500)


def test_an_empty_question_is_refused_before_any_model_call(bundle):
    fake = FakeLLM()
    with pytest.raises(ValueError, match="empty"):
        ask("   ", bundle, fake, 2500)
    assert fake.chat_calls == []


# --- insufficient evidence ---------------------------------------------------------------------------

def test_insufficient_evidence_with_no_claims_is_accepted(bundle):
    answer = "The evidence does not say what AAA plans for next year."
    result = ask("What are AAA's plans for next year?", bundle,
                 FakeLLM(replies=[reply(answer=answer, claims=(), insufficient=True)]), 2500)
    assert result.insufficient_evidence and result.answer == answer and result.claims == () and result.cited_ids == ()
    assert result.attempts == 1 and result.evidence                                   # the evidence shown is still returned


def test_insufficient_evidence_still_may_not_cite_unknown_ids(bundle):
    bad = reply(answer="Not enough.", claims=(("Nothing on plans.", ["AAA-MADE-UP-1"]),), insufficient=True)
    with pytest.raises(UngroundedAnswer) as exc:
        ask(QUESTION, bundle, FakeLLM(replies=[bad, bad]), 2500)
    assert exc.value.rejected_ids == ("AAA-MADE-UP-1",)


def test_an_empty_bundle_shows_no_evidence_and_accepts_insufficient(bundle):
    empty = build_bundle(ALL, "AAA", date(2020, 1, 1))
    fake = FakeLLM(replies=[reply(answer="There is no evidence.", claims=(), insufficient=True)])
    result = ask(QUESTION, empty, fake, 2500)
    assert result.evidence == () and result.insufficient_evidence and fake.chat_calls[0][0][1]["content"] == NO_EVIDENCE


# --- hard rules: no look-ahead, ticker isolation -------------------------------------------------------

@pytest.mark.parametrize("marker, hidden_id", [(FUTURE_MARKER, FUTURE.id), (OTHER_MARKER, OTHER.id)],
                         ids=["no-look-ahead", "ticker-isolation"])
def test_hidden_items_never_reach_the_model_and_cannot_be_cited(bundle, marker, hidden_id):
    # a question that matches the hidden item's words, and a model that tries to cite it twice
    cite_hidden = reply(claims=(("Results were restated.", [hidden_id]),))
    fake = FakeLLM(replies=[cite_hidden, cite_hidden])
    with pytest.raises(UngroundedAnswer) as exc:
        ask("annual results restated loss record profit", bundle, fake, 100_000)
    assert exc.value.rejected_ids == (hidden_id,)
    assert len(fake.chat_calls) == 2
    text_sent = "\n".join(m["content"] for messages, _ in fake.chat_calls for m in messages
                          if m["role"] != "assistant")                               # the model's own reply echoes the id
    assert marker not in all_text(fake) and marker not in text_sent
    assert f"[{hidden_id}]" not in text_sent


@pytest.mark.parametrize("marker", [FUTURE_MARKER, OTHER_MARKER])
def test_hidden_items_stay_out_on_a_successful_answer_too(bundle, marker):
    fake = FakeLLM(replies=[reply()])
    result = ask(f"annual results {marker.split('-')[1].lower()}", bundle, fake, 100_000)
    assert marker not in all_text(fake)
    assert all(i.date <= AS_OF and i.ticker in ("AAA", "MACRO") for i in result.evidence)


# --- token budget ---------------------------------------------------------------------------------------

def big_bundle():
    items = [EvidenceItem(f"AAA-PRICE-{AS_OF - timedelta(days=n)}", "AAA", "psxdata", "price", AS_OF - timedelta(days=n),
                          f"AAA closed at {200 + n}.00 PKR, volume {n}00 shares.") for n in range(60)]
    items += [EvidenceItem(f"AAA-ANN-{n}", "AAA", "psx_announcement", "announcement", AS_OF - timedelta(days=n),
                           f"AAA announcement {n}: " + "the board discussed the annual results and the dividend. " * 8)
              for n in range(30)]
    return build_bundle(items + [RES], "AAA", AS_OF)


@pytest.mark.parametrize("budget", [0, 60, 300, 900, 2500])
def test_the_evidence_shown_never_exceeds_the_budget(budget):
    fake = FakeLLM(replies=[reply(answer="Not enough.", claims=(), insufficient=True)])
    result = ask(QUESTION, big_bundle(), fake, budget)
    assert sum(item_cost(i, 3.0) for i in result.evidence) == result.context.used_tokens <= budget
    assert result.context.budget_tokens == budget and sum(result.context.dropped.values()) == 91 - len(result.evidence)
    evidence_message = fake.chat_calls[0][0][1]["content"]
    shown = [line.split("]")[0][1:] for line in evidence_message.splitlines() if line.startswith("[")]
    assert shown == [i.id for i in result.evidence]                                   # exactly the selected items, in order


def test_build_messages_shows_each_item_once_in_the_given_order():
    messages = build_messages("q?", (RES, ANN))
    body = messages[1]["content"]
    assert body.index("[AAA-RES-2026-08-20]") < body.index("[AAA-ANN-2026-09-01]") and body.count("[AAA-RES") == 1
