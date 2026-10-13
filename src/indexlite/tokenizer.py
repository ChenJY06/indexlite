"""A versioned tokenizer shared by document ingestion and query processing."""

import re
import unicodedata

TOKENIZER = {"version": 1, "normalization": "NFKC-casefold-NFC", "pattern": r"[^\W_]+"}
_WORDS = re.compile(TOKENIZER["pattern"], re.UNICODE)


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", unicodedata.normalize("NFKC", text).casefold())
    return _WORDS.findall(normalized)


def query_terms(query: str) -> list[str]:
    return sorted(set(tokenize(query)))
