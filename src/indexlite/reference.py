"""Exhaustive, preloaded comparison path; no posting-based candidate selection."""

from collections import Counter
from dataclasses import dataclass
from math import isclose

from .models import IndexLiteError, Ranking
from .ranking import bm25
from .search import search
from .storage import Index
from .tokenizer import query_terms, tokenize


@dataclass
class Reference:
    documents: list[tuple[int, int, Counter]]
    df: Counter
    average: float

    @classmethod
    def load(cls, index: Index):
        documents = []
        df: Counter = Counter()
        for document_id, text in index.connection.execute(
            "SELECT id, text FROM documents ORDER BY id"
        ):
            counts = Counter(tokenize(text))
            documents.append((document_id, sum(counts.values()), counts))
            df.update(counts.keys())
        total = sum(length for _, length, _ in documents)
        return cls(documents, df, total / len(documents) if documents else 0)

    def search(self, query: str, k: int, ranking: Ranking) -> tuple[list[tuple[int, float]], int]:
        terms = query_terms(query)
        scores = []
        for document_id, length, counts in self.documents:
            score = 0.0
            matched = False
            for term in terms:
                tf = counts.get(term, 0)
                if tf:
                    matched = True
                    score += bm25(
                        tf, self.df[term], length, len(self.documents), self.average, ranking
                    )
            if matched:
                scores.append((document_id, score))
        scores.sort(key=lambda pair: (-pair[1], pair[0]))
        return scores[:k], len(scores)


def agree(actual: list[tuple[int, float]], expected: list[tuple[int, float]]) -> bool:
    return len(actual) == len(expected) and all(
        aid == eid and isclose(a, e, rel_tol=1e-12, abs_tol=1e-12)
        for (aid, a), (eid, e) in zip(actual, expected, strict=True)
    )


def verify(index: Index, queries: list[str], k: int = 10) -> dict:
    index.validate()
    reference = Reference.load(index)
    # Retokenizing the stored text catches semantically corrupted postings as well.
    for document_id, length, counts in reference.documents:
        stored_length = index.connection.execute(
            "SELECT length FROM documents WHERE id=?", (document_id,)
        ).fetchone()[0]
        stored_counts = dict(
            index.connection.execute(
                "SELECT t.term, p.tf FROM postings p JOIN terms t ON t.id=p.term_id "
                "WHERE p.document_id=?",
                (document_id,),
            )
        )
        if length != stored_length or counts != stored_counts:
            raise IndexLiteError(
                f"verification failed: postings disagree with text in document {document_id}"
            )
    results = []
    for query in queries:
        actual = search(index, query, k)
        expected, candidates = reference.search(query, k, index.ranking)
        matched = actual.candidates == candidates and agree(
            [(hit.document_id, hit.score) for hit in actual.hits], expected
        )
        if not matched:
            raise IndexLiteError(f"indexed and exhaustive results disagree for query: {query!r}")
        results.append(dict(query=query, agreement=True, candidates=candidates))
    return dict(documents=index.count, verified_postings=True, queries=results)
