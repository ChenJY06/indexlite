import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .builder import build_index
from .demo import generate_demo
from .models import IndexLiteError, Ranking
from .reference import verify
from .search import search
from .storage import Index


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="indexlite", description="Persistent inverted index and BM25 search"
    )
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build or safely rebuild an index")
    build.add_argument("corpus", type=Path)
    build.add_argument("--index", type=Path, required=True)
    build.add_argument("--k1", type=float, default=1.2)
    build.add_argument("--b", type=float, default=0.75)
    build.add_argument(
        "--skip-errors", action="store_true", help="publish despite extraction errors"
    )
    find = commands.add_parser("search", help="search an existing index")
    find.add_argument("query")
    find.add_argument("--index", type=Path, required=True)
    find.add_argument("--top-k", type=int, default=10)
    find.add_argument("--k1", type=float, help="override the persisted setting")
    find.add_argument("--b", type=float, help="override the persisted setting")
    stats = commands.add_parser("stats", help="display index metadata and storage size")
    stats.add_argument("--index", type=Path, required=True)
    demo = commands.add_parser("demo", help="generate original deterministic sample notes")
    demo.add_argument("directory", type=Path)
    check = commands.add_parser("verify", help="check storage and compare exhaustive results")
    check.add_argument("--index", type=Path, required=True)
    check.add_argument("--query", action="append", dest="queries")
    check.add_argument("--top-k", type=int, default=10)
    benchmark = commands.add_parser(
        "benchmark", help="generate corpora and measure both search paths"
    )
    benchmark.add_argument("--out", type=Path, required=True, help="an empty output directory")
    benchmark.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 50000])
    benchmark.add_argument("--seed", type=int, default=1729)
    benchmark.add_argument("--repetitions", type=int, default=20)
    benchmark.add_argument("--warmup", type=int, default=3)
    benchmark.add_argument("--top-k", type=int, default=10)
    for command in (build, find, stats, demo, check, benchmark):
        command.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return root


def run(args: argparse.Namespace) -> dict:
    if args.command == "build":
        return asdict(
            build_index(
                args.corpus, args.index, Ranking(args.k1, args.b), skip_errors=args.skip_errors
            )
        )
    if args.command == "demo":
        return generate_demo(args.directory)
    if args.command == "benchmark":
        from .benchmark import run_benchmarks

        return run_benchmarks(
            args.out, args.sizes, args.seed, args.repetitions, args.warmup, args.top_k
        )
    with Index(args.index) as index:
        if args.command == "stats":
            return dict(index.metadata, index_bytes=index.path.stat().st_size)
        if args.command == "verify":
            return verify(
                index,
                args.queries or ["recursive function stack", "memory", "missingtoken", ""],
                args.top_k,
            )
        ranking = Ranking(
            args.k1 if args.k1 is not None else index.ranking.k1,
            args.b if args.b is not None else index.ranking.b,
        )
        return asdict(search(index, args.query, args.top_k, ranking))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        result = run(args)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        elif args.command == "search":
            print(f"{result['candidates']} matching documents")
            for rank, hit in enumerate(result["hits"], 1):
                print(f"{rank}. {hit['path']} | {hit['title']} | score={hit['score']:.6f}")
                print(f"   {hit['excerpt']}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except (IndexLiteError, OSError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"indexlite: {exc}", file=sys.stderr)
        return 2
