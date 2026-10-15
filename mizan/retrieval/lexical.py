"""BM25 with normalized words: stemming and a small glossary of standard finance abbreviations.

Plain BM25 (bm25.py) only matches identical words, so "replaced" does not find "replacement" and
"profit after tax" does not find "PAT". This module changes only how text is turned into words; the ranking
is the same BM25. It is deliberately generic and small:

  - Snowball (English) stemming: replaced / replacement -> replac, discoveries / discovery -> discoveri;
  - standard abbreviations are added NEXT TO the words they stand for, in documents and queries alike
    ("profit after taxation" also yields "pat", so a query using either form matches either form);
  - "genai" also counts as "ai".

It cannot bridge real vocabulary differences ("money paid out to shareholders" vs "dividend"); that needs
embeddings or a thesaurus. Plain BM25 stays available, so the two can be compared on the gold sets
(python -m mizan.retrieval.evaluate --retriever bm25-norm).
"""

import re

import snowballstemmer

from mizan.retrieval import bm25
from mizan.schemas import EvidenceBundle, EvidenceItem

_STEMMER = snowballstemmer.stemmer("english")

# (pattern, abbreviation): the abbreviation is appended after each match; plain finance vocabulary only
ABBREVIATIONS = [
    (re.compile(r"profit after tax(?:ation)?"), "pat"),
    (re.compile(r"profit before tax(?:ation)?"), "pbt"),
    (re.compile(r"earnings per share"), "eps"),
    (re.compile(r"annual general meeting"), "agm"),
    (re.compile(r"extra-?ordinary general meeting"), "eogm"),
    (re.compile(r"term finance certificates?"), "tfc"),
    (re.compile(r"capital adequacy ratio"), "car"),
    (re.compile(r"artificial intelligence"), "ai"),
    (re.compile(r"environmental,? social,? and governance"), "esg"),
]
ALSO_COUNTS_AS = {"genai": "ai", "tfcs": "tfc"}
# abbreviations are kept exactly as they are: the stemmer would turn "eps" into "ep"
PROTECTED = frozenset(a for _, a in ABBREVIATIONS) | frozenset(ALSO_COUNTS_AS.values())


def tokenize_normalized(text: str) -> list[str]:
    low = text.lower()
    for pattern, abbreviation in ABBREVIATIONS:
        low = pattern.sub(lambda m, a=abbreviation: f"{m.group(0)} {a}", low)
    tokens: list[str] = []
    for word in bm25.TOKEN_RE.findall(low):
        if word in bm25.STOPWORDS:
            continue
        tokens.append(word if word in PROTECTED else _STEMMER.stemWord(word))
        if word in ALSO_COUNTS_AS:
            tokens.append(ALSO_COUNTS_AS[word])
    return tokens


def search_normalized(bundle: EvidenceBundle, query: str, k: int = 5) -> list[tuple[EvidenceItem, float]]:
    """BM25 over normalized words; same signature and guarantees as bm25.search."""
    return bm25.search(bundle, query, k, tokenizer=tokenize_normalized)
