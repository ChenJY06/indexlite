from dataclasses import dataclass, field
from math import isfinite


class IndexLiteError(Exception):
    """An actionable input, extraction, or index error."""


@dataclass(frozen=True)
class Ranking:
    k1: float = 1.2
    b: float = 0.75

    def __post_init__(self) -> None:
        if not isfinite(self.k1) or self.k1 <= 0:
            raise IndexLiteError("k1 must be finite and greater than zero")
        if not isfinite(self.b) or not 0 <= self.b <= 1:
            raise IndexLiteError("b must be finite and between zero and one")


@dataclass(frozen=True)
class Hit:
    document_id: int
    score: float
    path: str
    title: str
    excerpt: str


@dataclass
class SearchResult:
    query: str
    terms: list[str]
    candidates: int
    hits: list[Hit]
    scoring_seconds: float
    formatting_seconds: float


@dataclass
class BuildReport:
    documents: int = 0
    terms: int = 0
    postings: int = 0
    tokens: int = 0
    source_bytes: int = 0
    index_bytes: int = 0
    average_length: float = 0
    timings: dict[str, float] = field(default_factory=dict)
    issues: list[dict[str, str]] = field(default_factory=list)
