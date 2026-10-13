import json
import math
import sqlite3
from pathlib import Path

from .models import IndexLiteError, Ranking
from .tokenizer import TOKENIZER

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
    text TEXT NOT NULL, length INTEGER NOT NULL CHECK (length > 0),
    source_bytes INTEGER NOT NULL CHECK (source_bytes >= 0)
);
CREATE TABLE terms (
    id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE,
    df INTEGER NOT NULL CHECK (df > 0)
);
CREATE TABLE postings (
    term_id INTEGER NOT NULL REFERENCES terms(id),
    document_id INTEGER NOT NULL REFERENCES documents(id),
    tf INTEGER NOT NULL CHECK (tf > 0),
    PRIMARY KEY (term_id, document_id)
) WITHOUT ROWID;
CREATE INDEX postings_by_document ON postings(document_id);
"""


def put_metadata(connection: sqlite3.Connection, data: dict) -> None:
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [
            (key, json.dumps(value, ensure_ascii=False, allow_nan=False))
            for key, value in data.items()
        ],
    )


class Index:
    """A read-only snapshot. Close it before rebuilding on Windows."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise IndexLiteError(f"index does not exist: {self.path}; run 'indexlite build' first")
        self.connection: sqlite3.Connection | None = None
        try:
            self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            self.connection.execute("PRAGMA query_only=ON")
            self.connection.execute("BEGIN")
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise IndexLiteError(f"incompatible schema version {version}; rebuild the index")
            self.metadata = {
                key: json.loads(value)
                for key, value in self.connection.execute("SELECT key, value FROM metadata")
            }
            if self.metadata["tokenizer"] != TOKENIZER:
                raise IndexLiteError("incompatible tokenizer configuration; rebuild the index")
            if self.metadata["schema_version"] != SCHEMA_VERSION:
                raise ValueError("schema metadata disagrees")
            self.ranking = Ranking(**self.metadata["ranking"])
            self.count = self.metadata["documents"]
            self.average = self.metadata["average_length"]
            integers = [self.metadata[key] for key in ("documents", "tokens", "terms", "postings")]
            if any(type(value) is not int or value < 0 for value in integers):
                raise ValueError("invalid corpus statistics")
            if not math.isfinite(self.average) or self.average < 0:
                raise ValueError("invalid average length")
            expected = self.metadata["tokens"] / self.count if self.count else 0
            if self.average != expected or (self.count > 0 and self.average == 0):
                raise ValueError("inconsistent average length")
            # Check required columns without traversing the corpus on every open.
            self.connection.execute(
                "SELECT id, path, title, text, length, source_bytes FROM documents LIMIT 0"
            )
            self.connection.execute("SELECT id, term, df FROM terms LIMIT 0")
            self.connection.execute("SELECT term_id, document_id, tf FROM postings LIMIT 0")
        except IndexLiteError:
            self.close()
            raise
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            self.close()
            raise IndexLiteError(f"damaged or incompatible index: {exc}; rebuild it") from exc

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def validate(self) -> None:
        db = self.connection
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("broken posting references")
            documents, tokens, source_bytes = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(length), 0), COALESCE(SUM(source_bytes), 0) "
                "FROM documents"
            ).fetchone()
            terms = db.execute("SELECT COUNT(*) FROM terms").fetchone()[0]
            postings = db.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
            measured = dict(
                documents=documents,
                tokens=tokens,
                source_bytes=source_bytes,
                terms=terms,
                postings=postings,
            )
            if any(self.metadata[key] != value for key, value in measured.items()):
                raise ValueError("metadata does not match stored corpus")
            bad_df = db.execute(
                "SELECT t.id FROM terms t LEFT JOIN postings p ON p.term_id=t.id "
                "GROUP BY t.id HAVING t.df != COUNT(p.document_id) OR t.df <= 0 LIMIT 1"
            ).fetchone()
            bad_length = db.execute(
                "SELECT d.id FROM documents d LEFT JOIN postings p ON p.document_id=d.id "
                "GROUP BY d.id HAVING d.length != COALESCE(SUM(p.tf), 0) OR d.length <= 0 LIMIT 1"
            ).fetchone()
            if (
                bad_df
                or bad_length
                or db.execute("SELECT 1 FROM postings WHERE tf <= 0 LIMIT 1").fetchone()
            ):
                raise ValueError("invalid document frequencies, lengths, or term frequencies")
        except (sqlite3.Error, ValueError, KeyError) as exc:
            raise IndexLiteError(f"damaged index: {exc}; rebuild it") from exc
