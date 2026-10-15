from datetime import date

from mizan.retrieval import bm25
from mizan.retrieval.bundle import build_bundle
from mizan.retrieval.lexical import search_normalized, tokenize_normalized
from mizan.schemas import EvidenceItem

D = date(2026, 6, 1)


def bundle(*texts):
    items = [EvidenceItem(f"AAA-{n}", "AAA", "psx", "announcement", D, t) for n, t in enumerate(texts)]
    return build_bundle(items, "AAA", D)


def test_word_forms_share_a_stem():
    assert tokenize_normalized("replaced") == tokenize_normalized("replacement") == tokenize_normalized("replace")
    assert tokenize_normalized("discoveries") == tokenize_normalized("discovery")
    assert tokenize_normalized("deposits") == tokenize_normalized("deposit")


def test_abbreviations_sit_next_to_the_words_they_stand_for():
    assert "pat" in tokenize_normalized("profit after taxation was Rs 5 million")
    assert "pat" in tokenize_normalized("PAT PKR 17.5 Bn")
    assert "eps" in tokenize_normalized("earnings per share of 56.35")
    assert "agm" in tokenize_normalized("Annual General Meeting notice")
    assert "tax" in tokenize_normalized("profit after tax")                      # the original words are kept too


def test_genai_counts_as_ai():
    assert "ai" in tokenize_normalized("Investment in AI & GenAI")
    assert "ai" in tokenize_normalized("GenAI")


def test_stopwords_dropped_and_digits_kept():
    assert tokenize_normalized("The cost of 17.5 billion") == ["cost", "17", "5", "billion"]
    assert tokenize_normalized("") == []


def test_plain_tokenizer_is_unchanged():
    assert bm25.tokenize("The Board approved a DIVIDEND of 3.00") == ["board", "approved", "dividend", "3", "00"]


def test_normalized_search_finds_what_plain_search_cannot():
    b = bundle("OGDC added reserves and the reserves replacement ratio was 236 percent.",
               "Board meeting notice for the quarter.", "PAT PKR 17.5 Bn higher fertilizer sales.")
    assert bm25.search(b, "reserves replaced", 3)[0][0].id == "AAA-0"            # shares "reserves" only
    assert search_normalized(b, "what share of reserves was replaced")[0][0].id == "AAA-0"
    assert bm25.search(b, "profit after tax", 3) == []
    assert search_normalized(b, "profit after tax")[0][0].id == "AAA-2"


def test_search_guarantees_still_hold():
    b = bundle("dividend declared", "unrelated text", "another notice")      # BM25 gives a word in half of 2 documents weight 0
    assert [i.id for i, _ in search_normalized(b, "dividends")] == ["AAA-0"]
    assert search_normalized(b, "") == [] and search_normalized(b, "the of and") == []
    assert search_normalized(build_bundle([], "AAA", D), "dividend") == []
    assert search_normalized(b, "dividend") == search_normalized(b, "dividend")            # deterministic


def test_abbreviations_are_not_stemmed():
    assert tokenize_normalized("EPS") == ["eps"]
    assert tokenize_normalized("eps agm pat") == ["eps", "agm", "pat"]
