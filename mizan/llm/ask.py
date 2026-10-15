"""Answer a question over an as-of evidence bundle with the local model (endpoint 8 of docs/api-plan.md, decision D13).

The caller builds the bundle with store.bundle(ticker, as_of), so the as-of filter and ticker isolation stay in the retrieval
layer. This module only narrows that bundle to a token budget (select_context) and never adds items, so the model is never
shown anything the bundle did not contain. An answer that cites an id the model was not shown is rejected: one corrective
retry, then UngroundedAnswer.

Plain Python, no web code. The prompt text lives in the constants below so it can be read and changed in one place.
"""

import time
from dataclasses import dataclass

from mizan.llm.base import LLM, BadOutput
from mizan.llm.schema_check import schema_errors
from mizan.retrieval.context import select_context
from mizan.schemas import EvidenceBundle, EvidenceItem

SYSTEM_PROMPT = (
    "You answer questions about a company listed on the Pakistan Stock Exchange, using only the evidence listed in the next "
    "message. Each evidence item starts with its id in square brackets, then its date, type and source.\n"
    "Rules:\n"
    "- Answer only from the listed evidence. Use no outside knowledge.\n"
    "- Every claim must cite the id of each evidence item it relies on, copied exactly as shown, without the brackets. "
    "Cite only ids from the listed evidence.\n"
    "- Do not state any number that does not appear in the evidence.\n"
    "- If the evidence is not enough to answer, say so in the answer and set insufficient_evidence to true.\n"
    "- Be brief: the answer is at most 2 sentences, with at most 3 claims of one short sentence each.\n"
    "Reply with only a JSON object with the fields answer, claims (each with text and evidence_ids) and insufficient_evidence."
)
EVIDENCE_HEADER = "Evidence ({count} items):"
EVIDENCE_ITEM = "[{id}] {date} | {type} | {source}\n{text}"
NO_EVIDENCE = "Evidence: none. There are no evidence items for this company on or before this date."
QUESTION = "Question: {question}"

# Sent after an answer that fails the grounding check, together with that answer. The chat options are deterministic, so
# repeating the same request would most likely repeat the same answer; naming the problem changes the prompt.
RETRY_PROMPT = ("That answer cannot be used: {problems}. Answer the question again using only the listed evidence. "
                "The only ids you may cite are: {allowed}. If the evidence is not enough, set insufficient_evidence to true.")

# Only keywords that schema_check.py supports. "At least one claim unless insufficient_evidence" cannot be written with them,
# so it is checked in code (grounding_problems).
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "insufficient_evidence": {"type": "boolean"},
    },
    "required": ["answer", "claims", "insufficient_evidence"],
    "additionalProperties": False,
}


class UngroundedAnswer(Exception):
    """The model's answer cited evidence it was not shown (or cited nothing) twice in a row. The message is meant for the UI."""

    def __init__(self, message: str, rejected_ids: tuple[str, ...], problems: tuple[str, ...]):
        super().__init__(message)
        self.rejected_ids = rejected_ids        # cited ids that were not among the evidence shown, from the last answer
        self.problems = problems


@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class AskTimings:
    retrieval_ms: float                     # choosing the context and building the prompt (the bundle is built by the caller)
    model_ms: float                         # wall-clock time of all model calls, including a retry


@dataclass(frozen=True)
class ContextUsed:
    budget_tokens: int
    used_tokens: int                        # estimated tokens of the evidence shown (select_context's count)
    dropped: dict[str, int]                 # item type -> items of the bundle left out to stay within the budget


@dataclass(frozen=True)
class AskResult:
    answer: str
    claims: tuple[Claim, ...]
    evidence: tuple[EvidenceItem, ...]      # exactly the items shown to the model, sorted by (date, id)
    cited_ids: tuple[str, ...]              # every id cited by a claim, in order of first citation; all are in evidence
    insufficient_evidence: bool
    model: str
    timings: AskTimings
    tokens_per_second: float | None         # from the accepted reply; None if the server did not report it
    prompt_tokens: int | None
    completion_tokens: int | None
    context: ContextUsed
    attempts: int                           # 1, or 2 when the first answer was rejected and the retry was accepted


def build_messages(question: str, evidence: tuple[EvidenceItem, ...]) -> list[dict]:
    """System rules, then the evidence (one block per item), then the question."""
    if evidence:
        blocks = [EVIDENCE_ITEM.format(id=i.id, date=i.date.isoformat(), type=i.type, source=i.source, text=i.text)
                  for i in evidence]
        evidence_text = EVIDENCE_HEADER.format(count=len(evidence)) + "\n\n" + "\n\n".join(blocks)
    else:
        evidence_text = NO_EVIDENCE
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": evidence_text},
        {"role": "user", "content": QUESTION.format(question=question)},
    ]


def grounding_problems(parsed: dict, allowed_ids: set[str]) -> tuple[list[str], list[str]]:
    """(problems, unknown cited ids) for a schema-valid answer. No problems: the answer is grounded in the evidence shown."""
    problems: list[str] = []
    unknown = _unique(i for c in parsed["claims"] for i in _clean_ids(c["evidence_ids"]) if i not in allowed_ids)
    if unknown:
        problems.append("it cites evidence ids that were not listed: " + ", ".join(unknown))
    if not parsed["insufficient_evidence"]:
        if not parsed["claims"]:
            problems.append("it has no claims, but insufficient_evidence is false")
        uncited = [n for n, c in enumerate(parsed["claims"], 1) if not _clean_ids(c["evidence_ids"])]
        if uncited:
            problems.append("claim " + ", ".join(map(str, uncited)) + " cites no evidence id")
    return problems, unknown


def ask(question: str, bundle: EvidenceBundle, llm: LLM, budget_tokens: int, *, clock=time.perf_counter) -> AskResult:
    """Raises ValueError (empty question), what llm.chat raises (LLMUnavailable, ModelMissing, BadOutput) and UngroundedAnswer."""
    question = question.strip()
    if not question:
        raise ValueError("the question is empty")

    started = clock()
    selection = select_context(bundle, query=question, budget_tokens=budget_tokens)
    messages = build_messages(question, selection.items)
    allowed = {i.id for i in selection.items}
    retrieval_ms = (clock() - started) * 1000

    started = clock()
    result = _chat(llm, messages)
    problems, unknown = grounding_problems(result.parsed, allowed)
    attempts = 1
    if problems:
        retry = [*messages, {"role": "assistant", "content": result.text},
                 {"role": "user", "content": RETRY_PROMPT.format(problems="; ".join(problems),
                                                                 allowed=", ".join(sorted(allowed)) or "none")}]
        result = _chat(llm, retry)
        problems, unknown = grounding_problems(result.parsed, allowed)
        attempts = 2
    model_ms = (clock() - started) * 1000
    if problems:
        raise UngroundedAnswer(f"Model '{result.model}' gave an answer that is not grounded in the evidence it was shown, "
                               f"after 2 attempts: {'; '.join(problems)}.", tuple(unknown), tuple(problems))

    parsed = result.parsed
    claims = tuple(Claim(c["text"].strip(), tuple(_clean_ids(c["evidence_ids"]))) for c in parsed["claims"])
    return AskResult(
        answer=parsed["answer"].strip(),
        claims=claims,
        evidence=selection.items,
        cited_ids=tuple(_unique(i for c in claims for i in c.evidence_ids)),
        insufficient_evidence=parsed["insufficient_evidence"],
        model=result.model,
        timings=AskTimings(retrieval_ms=round(retrieval_ms, 1), model_ms=round(model_ms, 1)),
        tokens_per_second=result.tokens_per_second,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        context=ContextUsed(selection.budget_tokens, selection.used_tokens, selection.dropped),
        attempts=attempts,
    )


def _chat(llm: LLM, messages: list[dict]):
    result = llm.chat(messages, ANSWER_SCHEMA)
    if result.parsed is None:                         # an LLM implementation must parse when given a schema; check anyway
        raise BadOutput(f"Model '{result.model}' returned no parsed JSON for the question.")
    errors = schema_errors(result.parsed, ANSWER_SCHEMA)          # OllamaClient has checked already; another LLM may not have
    if errors:
        raise BadOutput(f"Model '{result.model}' returned JSON that does not match the answer schema: {'; '.join(errors[:3])}.")
    return result


def _clean_ids(ids: list[str]) -> list[str]:
    """Ids as cited, without surrounding spaces or the square brackets the prompt shows them in; duplicates removed."""
    cleaned = (i.strip() for i in ids)
    cleaned = (i[1:-1].strip() if i.startswith("[") and i.endswith("]") else i for i in cleaned)
    return _unique(i for i in cleaned if i)


def _unique(values) -> list:
    return list(dict.fromkeys(values))
