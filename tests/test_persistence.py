import builtins
import json
import os
import sqlite3

import pytest

from indexlite import builder
from indexlite.builder import build_index
from indexlite.extract import extract_text
from indexlite.models import IndexLiteError
from indexlite.search import search
from indexlite.storage import Index

from .conftest import small_pdf, write_notes


def test_rebuild_add_change_remove(corpus, database):
    write_notes(corpus, {"a.txt": "apple", "b.txt": "banana"})
    build_index(corpus, database)
    (corpus / "a.txt").unlink()
    write_notes(corpus, {"b.txt": "carrot carrot", "c.md": "new apple"})
    build_index(corpus, database)
    with Index(database) as index:
        assert index.count == 2
        assert search(index, "banana").hits == []
        assert [hit.path for hit in search(index, "apple").hits] == ["c.md"]
        assert search(index, "carrot").hits[0].path == "b.txt"
        index.validate()


def test_failed_extraction_preserves_previous_index(corpus, database):
    write_notes(corpus, {"a.txt": "original searchable"})
    build_index(corpus, database)
    previous = database.read_bytes()
    (corpus / "b.txt").write_bytes(b"\xff\xfe")
    with pytest.raises(IndexLiteError, match="previous index preserved"):
        build_index(corpus, database)
    assert database.read_bytes() == previous
    assert not list(database.parent.glob(f".{database.name}.*"))
    with Index(database) as index:
        assert search(index, "original").hits[0].path == "a.txt"
    report = build_index(corpus, database, skip_errors=True)
    assert report.documents == 1
    assert report.issues[0]["kind"] == "error"


@pytest.mark.parametrize("failure", ["validation", "publication"])
def test_failed_finalization_preserves_index(corpus, database, monkeypatch, failure):
    write_notes(corpus, {"a.txt": "original"})
    build_index(corpus, database)
    previous = database.read_bytes()
    write_notes(corpus, {"a.txt": "replacement"})

    def fail(*_):
        if failure == "validation":
            raise IndexLiteError("validation failed")
        raise PermissionError("open reader")

    if failure == "validation":
        monkeypatch.setattr(Index, "validate", fail)
    else:
        monkeypatch.setattr(builder.os, "replace", fail)
    with pytest.raises(IndexLiteError, match="validation failed|close processes"):
        build_index(corpus, database)
    assert database.read_bytes() == previous
    assert not list(database.parent.glob(f".{database.name}.*"))


def test_open_reader_publication(corpus, database):
    write_notes(corpus, {"a.txt": "original"})
    build_index(corpus, database)
    with Index(database) as reader:
        write_notes(corpus, {"a.txt": "replacement"})
        if os.name == "nt":
            with pytest.raises(IndexLiteError, match="close processes"):
                build_index(corpus, database)
        else:
            build_index(corpus, database)
        assert search(reader, "original").hits[0].path == "a.txt"
    build_index(corpus, database)
    with Index(database) as index:
        assert search(index, "replacement").hits


def test_pdf_extraction_and_index(corpus, database):
    small_pdf(corpus / "note.pdf")
    assert "recursive function stack" in extract_text(corpus / "note.pdf")
    assert build_index(corpus, database).documents == 1
    with Index(database) as index:
        assert search(index, "recursive").hits[0].path == "note.pdf"


def test_blank_pdf_explains_ocr(corpus, database):
    small_pdf(corpus / "blank.pdf", "")
    with pytest.raises(IndexLiteError, match="no extractable text; OCR"):
        build_index(corpus, database)


def test_unreadable_and_damaged_pdf(corpus):
    missing = corpus / "missing.txt"
    with pytest.raises(IndexLiteError, match="cannot extract"):
        extract_text(missing)
    damaged = corpus / "damaged.pdf"
    damaged.write_bytes(b"not a PDF")
    with pytest.raises(IndexLiteError, match="cannot extract"):
        extract_text(damaged)


def test_permission_error_on_input(corpus, database, monkeypatch):
    write_notes(corpus, {"a.txt": "old valid"})
    build_index(corpus, database)
    previous = database.read_bytes()

    def unreadable(_):
        raise IndexLiteError("cannot extract: PermissionError: access denied")

    monkeypatch.setattr(builder, "extract_text", unreadable)
    with pytest.raises(IndexLiteError, match="access denied"):
        build_index(corpus, database)
    assert database.read_bytes() == previous


def test_optional_pdf_dependency_message(corpus, monkeypatch):
    small_pdf(corpus / "note.pdf")
    original_import = builtins.__import__

    def without_pypdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_pypdf)
    with pytest.raises(IndexLiteError, match=r"indexlite\[pdf\]"):
        extract_text(corpus / "note.pdf")


@pytest.mark.parametrize(
    "damage", ["missing", "bytes", "version", "metadata", "tokenizer", "columns"]
)
def test_clear_invalid_index_errors(corpus, database, damage):
    if damage == "missing":
        with pytest.raises(IndexLiteError, match="does not exist"):
            Index(database)
        return
    build_index(corpus, database)
    if damage == "bytes":
        database.write_bytes(b"this is not sqlite")
    else:
        with sqlite3.connect(database) as db:
            if damage == "version":
                db.execute("PRAGMA user_version=999")
            elif damage == "metadata":
                db.execute("UPDATE metadata SET value='bad json' WHERE key='documents'")
            elif damage == "tokenizer":
                db.execute(
                    "UPDATE metadata SET value=? WHERE key='tokenizer'",
                    (json.dumps({"version": 999}),),
                )
            else:
                db.execute("DROP TABLE postings")
    with pytest.raises(IndexLiteError, match="damaged|incompatible"):
        Index(database)


def test_validation_detects_count_damage(corpus, database):
    write_notes(corpus, {"a.txt": "apple apple"})
    build_index(corpus, database)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE postings SET tf=1")
    with Index(database) as index, pytest.raises(IndexLiteError, match="frequencies"):
        index.validate()


def test_source_unchanged_and_target_outside_corpus(corpus, database):
    write_notes(corpus, {"nested/a.txt": "source original"})
    original = {path: path.read_bytes() for path in corpus.rglob("*") if path.is_file()}
    with pytest.raises(IndexLiteError, match="outside"):
        build_index(corpus, corpus / "index.sqlite3")
    build_index(corpus, database)
    assert {path: path.read_bytes() for path in corpus.rglob("*") if path.is_file()} == original


def test_missing_corpus(database, tmp_path):
    with pytest.raises(IndexLiteError, match="corpus directory"):
        build_index(tmp_path / "missing", database)
