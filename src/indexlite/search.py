import sqlite3
from collections import defaultdict
from time import perf_counter

from .models import Hit, IndexLiteError, Ranking, SearchResult
from .ranking import bm25, top_k
from .snippets import excerpt
from .storage import Index
from .tokenizer import query_terms


def search(index: Index, query: str, k: int = 10, ranking: Ranking | None = None) -> SearchResult:
    if type(k) is not int or k <= 0:
        raise IndexLiteError("top-k must be a positive integer")
    began = perf_counter()
    terms = query_terms(query)
    scores: dict[int, float] = defaultdict(float)
    db = index.connection
    try:
        for term in terms:
            row = db.execute("SELECT id, df FROM terms WHERE term=?", (term,)).fetchone()
            if row is None:
                continue
            term_id, df = row
            for document_id, tf, length in db.execute(
                "SELECT p.document_id, p.tf, d.length FROM postings p "
                "JOIN documents d ON d.id=p.document_id WHERE p.term_id=?",
                (term_id,),
            ):
                scores[document_id] += bm25(
                    tf, df, length, index.count, index.average, ranking or index.ranking
                )
        selected = top_k(scores.items(), k)
        scoring_seconds = perf_counter() - began
        began = perf_counter()
        hits = []
        for document_id, score in selected:
            path, title, text = db.execute(
                "SELECT path, title, text FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            hits.append(Hit(document_id, score, path, title, excerpt(text, terms)))
        return SearchResult(
            query, terms, len(scores), hits, scoring_seconds, perf_counter() - began
        )
    except sqlite3.Error as exc:
        raise IndexLiteError(f"cannot search damaged index: {exc}; rebuild it") from exc
