import json
import socket
from datetime import date

import pytest
from starlette.testclient import TestClient

from api.main import create_app
from mizan.data.snapshot import write_snapshot
from mizan.llm import BadOutput, LLMUnavailable, ModelMissing
from mizan.llm.ask import ANSWER_SCHEMA
from mizan.llm.fake import FakeLLM
from mizan.retrieval.bundle import load_items
from mizan.schemas import EvidenceItem
from tests.test_api import AS_OF, FIXTURES, LOCAL, make_settings
from tests.test_llm_chat import Resp, Session, reply

FUTURE_MARKER = "QZX-FUTURE-5290"                 # only in an AAA item dated after AS_OF
OTHER_MARKER = "QZX-OTHER-TICKER-8812"            # only in a BBB item dated before AS_OF
MARKED = [
    EvidenceItem("AAA-ANN-2025-07-02", "AAA", "fake", "announcement", date(2025, 7, 2),
                 f"{FUTURE_MARKER} AAA restated its quarterly results and cut the dividend."),
    EvidenceItem("BBB-ANN-2025-06-20", "BBB", "fake", "announcement", date(2025, 6, 20),
                 f"{OTHER_MARKER} BBB quarterly results: dividend of 9.00 PKR per share."),
]
QUESTION = "What did AAA say about its quarterly results and dividend?"
GROUNDED = {"answer": "AAA approved quarterly results with revenue up 8% and an interim dividend of 3.00 PKR per share.",
            "claims": [{"text": "Revenue was up 8% year on year.", "evidence_ids": ["AAA-ANN-2025-04-25"]},
                       {"text": "An interim cash dividend of 3.00 PKR per share was declared.", "evidence_ids": ["AAA-ANN-2025-04-25"]}],
            "insufficient_evidence": False}


def answer(**changes) -> str:
    return json.dumps({**GROUNDED, **changes})


def marked_settings(tmp_path, **overrides):
    """The usual fixture snapshot plus the two marker items, so leaks through /ask can be detected."""
    snap = write_snapshot(load_items(FIXTURES) + MARKED, tmp_path / "snaps" / "fixture-marked")
    return make_settings(tmp_path, snapshot=str(snap), **overrides)


def app_with(tmp_path, fake, **overrides):
    return TestClient(create_app(marked_settings(tmp_path, **overrides), llm=fake))


def post_ask(client, **body):
    return client.post("/ask", json={"ticker": "AAA", "as_of": AS_OF, "question": QUESTION, **body})


def sent_text(fake: FakeLLM) -> str:
    return "\n".join(m["content"] for messages, _ in fake.chat_calls for m in messages)


# --- success -------------------------------------------------------------------------------------

def test_ask_returns_a_grounded_answer_with_its_evidence(tmp_path):
    fake = FakeLLM(replies=[answer()])
    r = post_ask(app_with(tmp_path, fake))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ticker", "as_of", "answer", "claims", "evidence", "cited_ids", "insufficient_evidence", "model",
                         "timings_ms", "tokens_per_second", "prompt_tokens", "completion_tokens", "context", "attempts"}
    assert body["ticker"] == "AAA" and body["as_of"] == AS_OF and body["answer"] == GROUNDED["answer"]
    assert body["claims"] == GROUNDED["claims"] and body["cited_ids"] == ["AAA-ANN-2025-04-25"]
    assert body["insufficient_evidence"] is False and body["attempts"] == 1 and body["model"] == "qwen3:8b"
    assert set(body["evidence"][0]) == {"id", "ticker", "source", "type", "date", "text"}
    assert set(body["cited_ids"]) <= {i["id"] for i in body["evidence"]}
    assert set(body["timings_ms"]) == {"retrieval", "model"} and body["timings_ms"]["model"] >= 0
    assert (body["tokens_per_second"], body["prompt_tokens"], body["completion_tokens"]) == (20.0, 30, 20)
    assert body["context"]["budget_tokens"] == 2500 and body["context"]["used_tokens"] <= 2500
    assert fake.chat_calls[0][1] is ANSWER_SCHEMA


def test_the_budget_setting_reaches_ask(tmp_path):
    fake = FakeLLM(replies=[answer(claims=[], insufficient_evidence=True)])
    body = post_ask(app_with(tmp_path, fake, ask_budget_tokens=40)).json()
    assert body["context"]["budget_tokens"] == 40 and body["context"]["used_tokens"] <= 40 and sum(body["context"]["dropped"].values()) > 0


def test_default_as_of_is_the_newest_date_in_the_snapshot(tmp_path):
    fake = FakeLLM(replies=[answer()])
    r = app_with(tmp_path, fake).post("/ask", json={"ticker": "aaa", "question": QUESTION})
    assert r.status_code == 200 and r.json()["as_of"] == "2025-07-20" and r.json()["ticker"] == "AAA"
    assert FUTURE_MARKER in sent_text(fake)               # with the newest date, the 2025-07-02 item is no longer in the future


def test_insufficient_evidence_is_a_200(tmp_path):
    fake = FakeLLM(replies=[answer(answer="The evidence does not cover this.", claims=[], insufficient_evidence=True)])
    body = post_ask(app_with(tmp_path, fake), question="Who is AAA's auditor?").json()
    assert body["insufficient_evidence"] is True and body["claims"] == [] and body["cited_ids"] == []


def test_a_retry_that_succeeds_is_a_200_with_two_attempts(tmp_path):
    fake = FakeLLM(replies=[answer(claims=[{"text": "x", "evidence_ids": ["NOPE-1"]}]), answer()])
    body = post_ask(app_with(tmp_path, fake)).json()
    assert body["attempts"] == 2 and body["cited_ids"] == ["AAA-ANN-2025-04-25"] and len(fake.chat_calls) == 2


# --- hard rules through /ask ------------------------------------------------------------------------

def test_no_look_ahead_through_ask(tmp_path):
    settings = marked_settings(tmp_path)
    c = TestClient(create_app(settings, llm=FakeLLM(replies=[answer()])))
    assert c.get("/evidence/AAA-ANN-2025-07-02").status_code == 200          # the marked item is in the snapshot

    fake = FakeLLM(replies=[answer()])
    body = post_ask(TestClient(create_app(settings, llm=fake)), question="restated quarterly results cut dividend").json()
    assert FUTURE_MARKER not in sent_text(fake) and FUTURE_MARKER not in json.dumps(body)
    assert all(i["date"] <= AS_OF for i in body["evidence"])

    cites_future = answer(claims=[{"text": "The dividend was cut.", "evidence_ids": ["AAA-ANN-2025-07-02"]}])
    fake = FakeLLM(replies=[cites_future, cites_future])
    r = post_ask(TestClient(create_app(settings, llm=fake)), question="restated quarterly results cut dividend")
    assert r.status_code == 502 and "AAA-ANN-2025-07-02" in r.json()["detail"]
    assert FUTURE_MARKER not in sent_text(fake)


def test_ticker_isolation_through_ask(tmp_path):
    settings = marked_settings(tmp_path)
    fake = FakeLLM(replies=[answer()])
    body = post_ask(TestClient(create_app(settings, llm=fake)), question="BBB quarterly results dividend 9.00").json()
    assert OTHER_MARKER not in sent_text(fake) and {i["ticker"] for i in body["evidence"]} <= {"AAA", "MACRO"}

    cites_other = answer(claims=[{"text": "A dividend of 9.00 PKR.", "evidence_ids": ["BBB-ANN-2025-06-20"]}])
    fake = FakeLLM(replies=[cites_other, cites_other])
    r = post_ask(TestClient(create_app(settings, llm=fake)), question="BBB quarterly results dividend 9.00")
    assert r.status_code == 502 and "BBB-ANN-2025-06-20" in r.json()["detail"]
    assert OTHER_MARKER not in sent_text(fake)


# --- errors -------------------------------------------------------------------------------------------

def test_unknown_ticker_is_404_and_the_model_is_not_called(tmp_path):
    fake = FakeLLM()
    r = post_ask(app_with(tmp_path, fake), ticker="ZZZZ")
    assert r.status_code == 404 and "Unknown ticker 'ZZZZ'" in r.json()["detail"] and fake.chat_calls == []


@pytest.mark.parametrize("body, field", [
    ({"ticker": "AAA", "as_of": "banana", "question": QUESTION}, "as_of"),
    ({"ticker": "AAA", "as_of": AS_OF, "question": ""}, "question"),
    ({"ticker": "AAA", "as_of": AS_OF, "question": "   "}, "question"),
    ({"ticker": "AAA", "as_of": AS_OF, "question": "x" * 501}, "question"),
    ({"ticker": "AAA", "as_of": AS_OF}, "question"),
    ({"as_of": AS_OF, "question": QUESTION}, "ticker"),
])
def test_bad_input_is_422_with_one_readable_sentence(tmp_path, body, field):
    fake = FakeLLM()
    r = app_with(tmp_path, fake).post("/ask", json=body)
    assert r.status_code == 422 and set(r.json()) == {"detail"}
    assert isinstance(r.json()["detail"], str) and field in r.json()["detail"] and fake.chat_calls == []


def test_a_500_character_question_is_accepted(tmp_path):
    assert post_ask(app_with(tmp_path, FakeLLM(replies=[answer()])), question="x" * 500).status_code == 200


def test_a_body_that_is_not_json_is_422(tmp_path):
    r = app_with(tmp_path, FakeLLM()).post("/ask", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


@pytest.mark.parametrize("error, status, text", [
    (LLMUnavailable("Ollama at http://mac:11434 is not reachable (ConnectionError)."), 503, "not reachable"),
    (ModelMissing("qwen3:4b-instruct", "http://mac:11434"), 503, "ollama pull qwen3:4b-instruct"),
    (BadOutput("Model 'qwen3:4b-instruct' did not return JSON matching the schema after 2 attempts."), 502, "after 2 attempts"),
])
def test_model_errors_map_to_status_codes(tmp_path, error, status, text):
    r = post_ask(app_with(tmp_path, FakeLLM(chat_error=error)))
    assert r.status_code == status and set(r.json()) == {"detail"} and text in r.json()["detail"]


def test_two_ungrounded_answers_are_502_naming_the_ids(tmp_path):
    bad = answer(claims=[{"text": "x", "evidence_ids": ["AAA-ANN-2025-04-25", "MADE-UP-7"]}])
    r = post_ask(app_with(tmp_path, FakeLLM(replies=[bad, bad])))
    assert r.status_code == 502 and set(r.json()) == {"detail"}
    assert "MADE-UP-7" in r.json()["detail"] and "not grounded" in r.json()["detail"]


def test_snapshot_not_usable_is_503(tmp_path):
    c = TestClient(create_app(make_settings(tmp_path, snapshot=str(tmp_path / "nope")), llm=FakeLLM()))
    r = post_ask(c)
    assert r.status_code == 503 and "snapshot is not usable" in r.json()["detail"]


def test_the_real_client_with_nothing_listening_is_503(tmp_path):
    c = TestClient(create_app(marked_settings(tmp_path, ollama_url="http://127.0.0.1:9")))
    r = post_ask(c)
    assert r.status_code == 503 and "not reachable" in r.json()["detail"]


def test_get_is_not_allowed(tmp_path):
    assert app_with(tmp_path, FakeLLM()).get("/ask").status_code == 405


# --- cut-off replies through the app's real Ollama client ------------------------------------------------
# Truncation is reported by the Ollama server (done_reason "length") and handled inside OllamaClient, which FakeLLM replaces,
# so these tests keep the client the app builds from its settings and give it a fake HTTP session (no network).

def ollama_app(tmp_path, *answers, **overrides):
    app = create_app(marked_settings(tmp_path, ollama_url="http://fake-ollama:11434", ollama_model="qwen3:4b-instruct",
                                     **overrides))
    app.state.llm.session = Session(*answers)
    return TestClient(app), app.state.llm.session


def cut_off(tail="TAIL-MARKER"):
    """A reply stopped at the num_predict limit: the JSON is unfinished."""
    return Resp(body=reply('{"answer": "OGDC reported its annual results' + " and more" * 200 + tail, done_reason="length"))


def test_a_cut_off_reply_then_a_valid_one_is_a_200(tmp_path):
    c, session = ollama_app(tmp_path, cut_off(), Resp(body=reply(answer())))
    r = post_ask(c)
    assert r.status_code == 200 and r.json()["answer"] == GROUNDED["answer"] and len(session.posts) == 2
    first, retry = (p["json"]["messages"] for p in session.posts)
    assert retry[:len(first)] == first and len(retry) == len(first) + 1        # only a short note is added
    assert retry[-1]["role"] == "user" and "cut off at the 1024-token limit" in retry[-1]["content"]
    assert "and more" not in retry[-1]["content"]                               # the cut-off reply is not resent


def test_two_cut_off_replies_are_a_502_without_the_reply_text(tmp_path, caplog):
    c, session = ollama_app(tmp_path, cut_off(), cut_off())
    with caplog.at_level("WARNING", logger="mizan.llm.ollama"):
        r = post_ask(c)
    assert r.status_code == 502 and set(r.json()) == {"detail"} and len(session.posts) == 2
    assert "cut off at the 1024-token limit" in r.json()["detail"] and "after 2 attempts" in r.json()["detail"]
    assert "TAIL-MARKER" not in r.json()["detail"] and "and more" not in r.json()["detail"]
    assert sum("TAIL-MARKER" in rec.getMessage() for rec in caplog.records) == 2       # the tail is in the server log


def test_the_num_predict_setting_reaches_every_chat_request(tmp_path):
    c, session = ollama_app(tmp_path, cut_off(), cut_off(), ollama_num_predict=700, ollama_num_ctx=4096)
    r = post_ask(c)
    assert [p["json"]["options"]["num_predict"] for p in session.posts] == [700, 700]
    assert all(p["json"]["options"]["num_ctx"] == 4096 for p in session.posts)
    assert r.status_code == 502 and "cut off at the 700-token limit" in r.json()["detail"]


# --- contract and no network --------------------------------------------------------------------------

def test_openapi_lists_ask_as_a_post_with_its_body(tmp_path):
    spec = app_with(tmp_path, FakeLLM()).get("/openapi.json").json()
    assert "post" in spec["paths"]["/ask"] and {"ticker", "as_of", "question"} <= set(spec["components"]["schemas"]["AskIn"]["properties"])


def test_ask_with_a_fake_model_opens_no_outside_connection(tmp_path, monkeypatch):
    attempts = []
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in LOCAL:
            attempts.append(host)
            raise AssertionError(f"/ask tried to connect to {host}")
        return real_connect(self, address, *args, **kwargs)

    c = app_with(tmp_path, FakeLLM(replies=[answer()]), live_fetching_enabled=True)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    assert post_ask(c).status_code == 200 and attempts == []
