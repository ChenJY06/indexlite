import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter

from .extract import SUPPORTED, document_title, extract_text
from .models import BuildReport, IndexLiteError, Ranking
from .storage import SCHEMA, SCHEMA_VERSION, Index, put_metadata
from .tokenizer import TOKENIZER, tokenize


def build_index(
    corpus: str | Path,
    target: str | Path,
    ranking: Ranking | None = None,
    *,
    skip_errors: bool = False,
) -> BuildReport:
    began = perf_counter()
    ranking = ranking or Ranking()
    corpus, target = Path(corpus).resolve(), Path(target).resolve()
    if not corpus.is_dir():
        raise IndexLiteError(f"corpus directory does not exist: {corpus}")
    if target.is_relative_to(corpus):
        raise IndexLiteError("put the index outside the source corpus directory")
    report = BuildReport(
        timings={
            key: 0.0
            for key in ("extraction", "tokenization", "construction", "validation", "publication")
        }
    )
    temporary = None
    db = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(handle)
        temporary = Path(name)
        db = sqlite3.connect(temporary)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript(SCHEMA)
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        db.execute("BEGIN IMMEDIATE")
        term_ids: dict[str, int] = {}
        frequencies: Counter[int] = Counter()
        paths = sorted(corpus.rglob("*"), key=lambda path: path.relative_to(corpus).as_posix())
        for path in paths:
            relative = path.relative_to(corpus).as_posix()
            if path.is_symlink():
                report.issues.append(
                    dict(path=relative, kind="unsupported", message="symlink skipped")
                )
                continue
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED:
                report.issues.append(
                    dict(path=relative, kind="unsupported", message="unsupported file type")
                )
                continue
            tick = perf_counter()
            try:
                text = extract_text(path)
                byte_count = path.stat().st_size
            except (IndexLiteError, OSError) as exc:
                report.issues.append(dict(path=relative, kind="error", message=str(exc)))
                if not skip_errors:
                    raise IndexLiteError(
                        f"{relative}: {exc}; rebuild aborted, previous index preserved"
                    ) from exc
                continue
            finally:
                report.timings["extraction"] += perf_counter() - tick
            tick = perf_counter()
            counts = Counter(tokenize(text))
            report.timings["tokenization"] += perf_counter() - tick
            if not counts:
                report.issues.append(
                    dict(path=relative, kind="empty", message="no searchable tokens; skipped")
                )
                continue
            tick = perf_counter()
            report.documents += 1
            length = sum(counts.values())
            db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.documents,
                    relative,
                    document_title(text, relative),
                    text,
                    length,
                    byte_count,
                ),
            )
            rows = []
            for term, tf in sorted(counts.items()):
                if term not in term_ids:
                    term_id = len(term_ids) + 1
                    term_ids[term] = term_id
                    db.execute("INSERT INTO terms VALUES (?, ?, 1)", (term_id, term))
                term_id = term_ids[term]
                frequencies[term_id] += 1
                rows.append((term_id, report.documents, tf))
            db.executemany("INSERT INTO postings VALUES (?, ?, ?)", rows)
            report.postings += len(rows)
            report.tokens += length
            report.source_bytes += byte_count
            report.timings["construction"] += perf_counter() - tick
        tick = perf_counter()
        db.executemany(
            "UPDATE terms SET df=? WHERE id=?", [(df, tid) for tid, df in frequencies.items()]
        )
        report.terms = len(term_ids)
        report.average_length = report.tokens / report.documents if report.documents else 0
        put_metadata(
            db,
            dict(
                schema_version=SCHEMA_VERSION,
                tokenizer=TOKENIZER,
                ranking=dict(k1=ranking.k1, b=ranking.b),
                documents=report.documents,
                tokens=report.tokens,
                terms=report.terms,
                postings=report.postings,
                average_length=report.average_length,
                source_bytes=report.source_bytes,
            ),
        )
        db.commit()
        db.close()
        db = None
        report.timings["construction"] += perf_counter() - tick
        tick = perf_counter()
        with Index(temporary) as index:
            index.validate()
        report.timings["validation"] = perf_counter() - tick
        report.index_bytes = temporary.stat().st_size
        tick = perf_counter()
        try:
            os.replace(temporary, target)
        except PermissionError as exc:
            raise IndexLiteError(
                "cannot publish index: close processes holding the index open and retry; "
                "previous index preserved"
            ) from exc
        report.timings["publication"] = perf_counter() - tick
        report.timings["total"] = perf_counter() - began
        return report
    except (OSError, sqlite3.Error) as exc:
        raise IndexLiteError(f"cannot build index: {exc}; previous index preserved") from exc
    finally:
        if db is not None:
            db.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
