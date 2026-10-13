import math
import random
import sqlite3
from collections import Counter

import pytest

from indexlite.builder import build_index
from indexlite.models import IndexLiteError, Ranking
from indexlite.ranking import bm25, top_k
from indexlite.reference import Reference, agree, verify
from indexlite.search import search
from indexlite.snippets import excerpt
from indexlite.storage import Index
from indexlite.tokenizer import query_terms, tokenize

from .conftest import write_notes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Straße STRASSE café café ＡＢＣ", ["strasse", "strasse", "café", "café", "abc"]),
        (
            "recursive_function first-in C++ isn't 3.14 2026",
            ["recursive", "function", "first", "in", "c", "isn", "t", "3", "14", "2026"],
        ),
        ("Σ σ ς 中文 東京", ["σ", "σ", "σ", "中文", "東京"]),
        ("   —_!", []),
        ("", []),
    ],
)
def test_tokenizer(text, expected):
    assert tokenize(text) == expected


def test_unique_query_terms():
    assert query_terms("Stack STACK recursive stack") == ["recursive", "stack"]


def test_storage_counts(corpus, database):
    write_notes(
        corpus,
        {"b.md": "apple carrot", "a.txt": "apple apple banana", "c.txt": "banana carrot carrot"},
    )
    report = build_index(corpus, database)
    assert (report.documents, report.tokens, report.terms, report.postings) == (3, 8, 3, 6)
    assert report.average_length == 8 / 3
    with Index(database) as index:
        db = index.connection
        assert db.execute("SELECT id, path, length FROM documents ORDER BY id").fetchall() == [
            (1, "a.txt", 3),
            (2, "b.md", 2),
            (3, "c.txt", 3),
        ]
        assert db.execute("SELECT term, df FROM terms ORDER BY term").fetchall() == [
            ("apple", 2),
            ("banana", 2),
            ("carrot", 2),
        ]
        assert db.execute(
            "SELECT t.term, p.document_id, p.tf FROM terms t JOIN postings p "
            "ON p.term_id=t.id ORDER BY t.term, p.document_id"
        ).fetchall() == [
            ("apple", 1, 2),
            ("apple", 2, 1),
            ("banana", 1, 1),
            ("banana", 3, 1),
            ("carrot", 2, 1),
            ("carrot", 3, 2),
        ]
        index.validate()
        result = search(index, "apple banana")
        # Independently calculated for N=3, df=2, average length=8/3.
        idf = math.log(1 + 1.5 / 2.5)
        apple_a = idf * 2 * 2.2 / (2 + 1.2 * (0.25 + 0.75 * 3 / (8 / 3)))
        banana_a = idf * 1 * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 3 / (8 / 3)))
        apple_b = idf * 1 * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 2 / (8 / 3)))
        assert [hit.path for hit in result.hits] == ["a.txt", "b.md", "c.txt"]
        assert [hit.score for hit in result.hits] == pytest.approx(
            [apple_a + banana_a, apple_b, banana_a], rel=1e-13
        )
        assert search(index, "apple apple BANANA").hits == result.hits
        assert search(index, "apple banana unknown").hits == result.hits


def test_manual_ranking(corpus, database):
    write_notes(
        corpus,
        {
            "a.txt": "recursive recursive function stack",
            "b.txt": "function stack heap heap heap heap",
            "c.txt": "unrelated topic",
        },
    )
    build_index(corpus, database)
    with Index(database) as index:
        assert [h.path for h in search(index, "recursive function stack").hits] == [
            "a.txt",
            "b.txt",
        ]


@pytest.mark.parametrize("ranking", [Ranking(0.7, 0), Ranking(2.1, 1), Ranking()])
def test_configurable_ranking(corpus, database, ranking):
    write_notes(corpus, {"a.txt": "apple apple", "b.txt": "apple banana banana"})
    build_index(corpus, database, ranking)
    with Index(database) as index:
        assert index.ranking == ranking
        result = search(index, "apple")
        expected = (
            math.log(1 + 0.5 / 2.5)
            * 2
            * (ranking.k1 + 1)
            / (2 + ranking.k1 * (1 - ranking.b + ranking.b * 2 / 2.5))
        )
        assert result.hits[0].score == pytest.approx(expected)


@pytest.mark.parametrize(
    ("k1", "b"),
    [(0, 0.75), (-1, 0), (math.nan, 0), (math.inf, 1), (1, -0.1), (1, 1.1), (1, math.nan)],
)
def test_bad_ranking(k1, b):
    with pytest.raises(IndexLiteError):
        Ranking(k1, b)


def test_empty_corpus_and_files(corpus, database):
    write_notes(corpus, {"empty.txt": " ", "punctuation.md": "--- !", "image.png": "unsupported"})
    report = build_index(corpus, database)
    assert report.documents == report.tokens == report.terms == report.postings == 0
    assert Counter(issue["kind"] for issue in report.issues) == {"empty": 2, "unsupported": 1}
    with Index(database) as index:
        assert index.count == index.average == 0
        assert search(index, "anything").hits == []
        assert search(index, "").candidates == 0
        verify(index, ["", "missing"])
    assert bm25(0, 0, 0, 0, 0, Ranking()) == 0


@pytest.mark.parametrize("k", [1, 2, 3, 10, 100])
def test_tie_breaking_and_k(corpus, database, k):
    write_notes(corpus, {"z.txt": "same term", "b.txt": "same term", "a.txt": "same term"})
    build_index(corpus, database)
    with Index(database) as index:
        assert [h.path for h in search(index, "same", k).hits] == ["a.txt", "b.txt", "z.txt"][:k]
        assert search(index, "unknown").hits == []
        assert search(index, " -- ").hits == []


@pytest.mark.parametrize("k", [0, -1, 1.5])
def test_invalid_k(corpus, database, k):
    build_index(corpus, database)
    with Index(database) as index, pytest.raises(IndexLiteError, match="positive integer"):
        search(index, "query", k)


def test_heap_against_independent_sort():
    rng = random.Random(971)
    for count in [0, 1, 2, 50, 301]:
        scores = [(i, float(rng.randrange(12))) for i in range(count)]
        rng.shuffle(scores)
        reference = sorted(scores, key=lambda pair: (-pair[1], pair[0]))
        for k in [1, 2, 9, 50, 400]:
            assert top_k(iter(scores), k) == reference[:k]


def test_search_only_reads_posting_candidates(corpus, database):
    write_notes(corpus, {f"{i:04}.txt": f"common id{i}" for i in range(100)})
    build_index(corpus, database)
    with Index(database) as index:
        statements = []
        index.connection.set_trace_callback(statements.append)
        result = search(index, "id17")
        assert result.candidates == 1
        assert result.hits[0].path == "0017.txt"
        assert not any("SELECT id, text FROM documents" in stmt for stmt in statements)
        assert all("WHERE" in stmt for stmt in statements if stmt.startswith("SELECT"))
        plan = index.connection.execute(
            "EXPLAIN QUERY PLAN SELECT document_id FROM postings WHERE term_id=?", (1,)
        ).fetchall()
        assert any("SEARCH" in row[3] and "PRIMARY KEY" in row[3] for row in plan)


def test_exhaustive_agreement(corpus, database):
    rng = random.Random(214)
    vocabulary = ["alpha", "beta", "γ", "東京", "system"]
    write_notes(
        corpus,
        {
            f"{i:03}.txt": " ".join(rng.choices(vocabulary, k=rng.randrange(1, 70)))
            for i in range(40)
        },
    )
    build_index(corpus, database)
    with Index(database) as index:
        ref = Reference.load(index)
        for query in ["", "missing", "alpha", "system beta", "Γ Γ 東京 unknown"]:
            for k in [1, 5, 30, 100]:
                actual = search(index, query, k)
                expected, count = ref.search(query, k, index.ranking)
                assert actual.candidates == count
                assert agree([(hit.document_id, hit.score) for hit in actual.hits], expected)


def test_snippet_unicode_and_relevance():
    text = "unrelated " * 40 + "Straße recursive function stack" + " trailing" * 40
    result = excerpt(text, ["strasse", "recursive", "function", "stack"])
    assert "Straße recursive function stack" in result
    assert len(result) <= 182
    assert result.startswith("…")


def test_semantic_corruption_detected(corpus, database):
    write_notes(corpus, {"a.txt": "apple banana"})
    build_index(corpus, database)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE documents SET text='different words'")
    with Index(database) as index, pytest.raises(IndexLiteError, match="postings disagree"):
        verify(index, ["apple"])
