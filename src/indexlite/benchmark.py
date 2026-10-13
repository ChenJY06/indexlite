import csv
import hashlib
import json
import os
import platform
import sqlite3
import statistics
import sys
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.util import find_spec
from math import ceil
from pathlib import Path
from time import perf_counter

from . import __version__
from .builder import build_index
from .demo import fresh_directory, generate_demo, generate_synthetic
from .models import IndexLiteError
from .reference import Reference, agree
from .search import search
from .storage import SCHEMA_VERSION, Index
from .tokenizer import TOKENIZER

SYNTHETIC_QUERIES = [
    "quasar",
    "system",
    "memory",
    "quasar memory",
    "term000 term001",
    "doc000000",
    "missingtoken",
    "system quasar",
]
DEMO_QUERIES = ["recursive function stack", "memory", "queue", "unicode", "the", "missingtoken"]


def p95(values: list[float]) -> float:
    return sorted(values)[ceil(0.95 * len(values)) - 1]


def environment() -> dict:
    return dict(
        python=sys.version,
        sqlite=sqlite3.sqlite_version,
        os=platform.platform(),
        cpu=os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or "unreported",
        logical_cpus=os.cpu_count(),
        indexlite=__version__,
        unicode_database=unicodedata.unidata_version,
        packages={
            name: version(name)
            for name in ("pytest", "ruff", "pypdf", "matplotlib")
            if find_spec(name) is not None
        },
    )


def _measure(index: Index, reference: Reference, query: str, k: int, indexed_first: bool) -> dict:
    def indexed():
        began = perf_counter()
        result = search(index, query, k)
        return result, (perf_counter() - began) * 1000

    def exhaustive():
        began = perf_counter()
        result = reference.search(query, k, index.ranking)
        return result, (perf_counter() - began) * 1000

    if indexed_first:
        actual, total_ms = indexed()
        (expected, candidates), reference_ms = exhaustive()
    else:
        (expected, candidates), reference_ms = exhaustive()
        actual, total_ms = indexed()
    agreement = actual.candidates == candidates and agree(
        [(hit.document_id, hit.score) for hit in actual.hits], expected
    )
    if not agreement:
        raise IndexLiteError(f"benchmark stopped: results disagree for {query!r}")
    return dict(
        query=query,
        candidates=candidates,
        agreement=agreement,
        indexed_scoring_ms=actual.scoring_seconds * 1000,
        formatting_ms=actual.formatting_seconds * 1000,
        indexed_total_ms=total_ms,
        reference_ms=reference_ms,
        order="indexed-first" if indexed_first else "reference-first",
    )


def benchmark_corpus(
    corpus: Path,
    database: Path,
    queries: list[str],
    repetitions: int,
    warmup: int,
    k: int,
    characteristics: dict,
) -> tuple[dict, list[dict]]:
    build = build_index(corpus, database)
    # A fresh connection per query is a first-query measurement, not a cold-cache claim.
    first = []
    for query in queries:
        began = perf_counter()
        with Index(database) as index:
            open_ms = (perf_counter() - began) * 1000
            result = search(index, query, k)
            first.append(
                dict(
                    query=query,
                    open_ms=open_ms,
                    scoring_ms=result.scoring_seconds * 1000,
                    formatting_ms=result.formatting_seconds * 1000,
                )
            )
    began = perf_counter()
    with Index(database) as index:
        open_ms = (perf_counter() - began) * 1000
        sqlite_read_settings = {
            key: index.connection.execute(f"PRAGMA {key}").fetchone()[0]
            for key in ("cache_size", "page_size", "journal_mode")
        }
        began = perf_counter()
        reference = Reference.load(index)
        reference_load_ms = (perf_counter() - began) * 1000
        # Check agreement before accepting performance data.
        for query in queries:
            _measure(index, reference, query, k, True)
        for _ in range(warmup):
            for query in queries:
                _measure(index, reference, query, k, True)
        rows = []
        for repetition in range(repetitions):
            for position, query in enumerate(queries):
                row = _measure(index, reference, query, k, (repetition + position) % 2 == 0)
                rows.append(dict(documents=index.count, repetition=repetition, **row))
    summaries = []
    for query in queries:
        samples = [row for row in rows if row["query"] == query]
        summary = dict(query=query, candidates=samples[0]["candidates"], agreement=True)
        for field in ("indexed_scoring_ms", "formatting_ms", "indexed_total_ms", "reference_ms"):
            values = [row[field] for row in samples]
            summary[field] = dict(median=statistics.median(values), p95=p95(values))
        summary["scoring_speedup"] = (
            summary["reference_ms"]["median"] / summary["indexed_scoring_ms"]["median"]
        )
        summaries.append(summary)
    return dict(
        characteristics=characteristics,
        build=asdict(build),
        open_ms=open_ms,
        reference_load_ms=reference_load_ms,
        first_queries=first,
        queries=summaries,
        documents_per_second=build.documents / build.timings["total"],
        sqlite_read_settings=sqlite_read_settings,
    ), rows


def write_report(output: Path, data: dict) -> None:
    lines = [
        "# IndexLite benchmark run",
        "",
        f"Measured at {data['measured_at_utc']}.",
        "",
        f"Seed {data['seed']}; {data['repetitions']} repetitions after {data['warmup']} warm-ups; "
        f"top-k {data['top_k']}.",
        "",
        "Indexed scoring includes query tokenization, posting reads, BM25 and heap selection. "
        "Formatting includes fetching the selected text and generating snippets. "
        "The exhaustive reference scans preloaded term-frequency dictionaries and fully sorts "
        "matches; its loading and snippet work are excluded from the speedup comparison.",
        "",
        "First-query measurements use new connections after the build. OS and SQLite cache "
        "conditions are uncontrolled; none of these measurements claim a cold cache.",
        "",
        "Agreement validates execution consistency, not relevance. Synthetic queries are "
        "designed experiments, not user traffic. No memory measurements are reported.",
        "",
    ]
    for corpus in data["corpora"]:
        build = corpus["build"]
        lines += [
            f"## {corpus['name']} ({build['documents']:,} documents)",
            "",
            f"Build: {build['timings']['total']:.3f} s; "
            f"{corpus['documents_per_second']:,.0f} documents/s. "
            f"Source: {build['source_bytes']:,} bytes; index: {build['index_bytes']:,} bytes.",
            "",
            "| Query | Candidates | Indexed median/p95 ms | Reference median/p95 ms | "
            "Format median ms | Scoring speedup | Agreement |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for query in corpus["queries"]:
            indexed, reference = query["indexed_scoring_ms"], query["reference_ms"]
            lines.append(
                f"| `{query['query']}` | {query['candidates']:,} | "
                f"{indexed['median']:.4f}/{indexed['p95']:.4f} | "
                f"{reference['median']:.4f}/{reference['p95']:.4f} | "
                f"{query['formatting_ms']['median']:.4f} | "
                f"{query['scoring_speedup']:.2f}× | yes |"
            )
        lines += [
            "",
            "Build boundaries (seconds): "
            + ", ".join(f"{key}={value:.4f}" for key, value in build["timings"].items()),
            "",
            f"Open: {corpus['open_ms']:.4f} ms; reference preload: "
            f"{corpus['reference_load_ms']:.2f} ms.",
            "",
        ]
    lines += [
        "## Environment",
        "",
        "```json",
        json.dumps(data["environment"], indent=2),
        "```",
        "",
        "See summary.json for first-query measurements and raw.csv for every warm sample.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_results(output: Path, data: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    synthetic = [corpus for corpus in data["corpora"] if corpus["name"] != "demo"]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    sizes = [corpus["build"]["documents"] for corpus in synthetic]
    for query in ("quasar", "system", "memory", "missingtoken"):
        for field, style in (("indexed_scoring_ms", "-"), ("reference_ms", "--")):
            values = [
                next(q for q in c["queries"] if q["query"] == query)[field]["median"]
                for c in synthetic
            ]
            axes[0].plot(sizes, values, style, marker="o", label=f"{query}: {field.split('_')[0]}")
    axes[0].set(
        xscale="log",
        yscale="log",
        xlabel="Documents",
        ylabel="Median scoring latency (ms)",
        title="Warm queries; reference data preloaded",
    )
    axes[0].legend(fontsize=7)
    for label, field in (("Source", "source_bytes"), ("SQLite index", "index_bytes")):
        axes[1].plot(
            sizes, [c["build"][field] / 1024**2 for c in synthetic], marker="o", label=label
        )
    axes[1].set(xscale="log", xlabel="Documents", ylabel="Size (MiB)", title="Persisted storage")
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(output / "latency-and-size.png", dpi=160)
    plt.close(figure)


def run_benchmarks(
    output: str | Path,
    sizes: list[int],
    seed: int = 1729,
    repetitions: int = 20,
    warmup: int = 3,
    k: int = 10,
) -> dict:
    if not sizes or any(size <= 0 for size in sizes) or len(set(sizes)) != len(sizes):
        raise IndexLiteError("benchmark sizes must be distinct positive integers")
    if repetitions < 2 or warmup < 0 or k <= 0:
        raise IndexLiteError("use at least 2 repetitions, nonnegative warmup, and positive top-k")
    if find_spec("matplotlib") is None:
        raise IndexLiteError("plots require: pip install 'indexlite[bench]'")
    output = fresh_directory(output)
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    data = dict(
        measured_at_utc=datetime.now(UTC).isoformat(),
        seed=seed,
        repetitions=repetitions,
        warmup=warmup,
        top_k=k,
        environment=environment(),
        index_configuration={
            "schema_version": SCHEMA_VERSION,
            "tokenizer": TOKENIZER,
            "ranking": {"k1": 1.2, "b": 0.75},
        },
        corpora=[],
    )
    all_rows = []
    for size in sizes:
        corpus = output / "corpora" / str(size)
        print(f"Generating {size:,} synthetic documents", file=sys.stderr, flush=True)
        characteristics = generate_synthetic(corpus, size, seed)
        print(f"Building and querying the {size:,}-document index", file=sys.stderr, flush=True)
        summary, rows = benchmark_corpus(
            corpus,
            output / f"index-{size}.sqlite3",
            SYNTHETIC_QUERIES,
            repetitions,
            warmup,
            k,
            characteristics,
        )
        summary["name"] = f"synthetic-{size}"
        data["corpora"].append(summary)
        all_rows += [dict(corpus=summary["name"], **row) for row in rows]
        (output / "summary.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Benchmarked {size:,} synthetic documents", file=sys.stderr, flush=True)
    corpus = output / "corpora" / "demo"
    generate_demo(corpus)
    summary, rows = benchmark_corpus(
        corpus,
        output / "index-demo.sqlite3",
        DEMO_QUERIES,
        repetitions,
        warmup,
        k,
        {"original_generated_notes": True},
    )
    summary["name"] = "demo"
    data["corpora"].append(summary)
    all_rows += [dict(corpus="demo", **row) for row in rows]
    (output / "summary.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    with (output / "raw.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    data["raw_samples"] = len(all_rows)
    data["raw_csv_sha256"] = hashlib.sha256((output / "raw.csv").read_bytes()).hexdigest()
    data["finished_at_utc"] = datetime.now(UTC).isoformat()
    (output / "summary.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    write_report(output, data)
    plot_results(output, data)
    return dict(
        output=str(output),
        corpora=len(data["corpora"]),
        agreement=True,
        summary=str(output / "summary.json"),
        raw=str(output / "raw.csv"),
        report=str(output / "report.md"),
        plot=str(output / "latency-and-size.png"),
    )
