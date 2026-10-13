import json
import subprocess
import sys

import pytest

from .conftest import write_notes


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "indexlite", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_persistence_across_cli_processes(corpus, database):
    write_notes(corpus, {"a.md": "# Stack\nrecursive function stack", "b.txt": "queue jobs"})
    built = cli("build", corpus, "--index", database, "--json")
    assert built.returncode == 0, built.stderr
    assert json.loads(built.stdout)["documents"] == 2
    searched = cli(
        "search", "recursive function stack", "--index", database, "--top-k", 1, "--json"
    )
    assert searched.returncode == 0, searched.stderr
    result = json.loads(searched.stdout)
    assert result["hits"][0]["path"] == "a.md"
    assert result["hits"][0]["title"] == "Stack"
    assert result["hits"][0]["score"] > 0
    assert "recursive function stack" in result["hits"][0]["excerpt"]
    assert json.loads(cli("stats", "--index", database, "--json").stdout)["documents"] == 2
    assert json.loads(cli("verify", "--index", database, "--query", "stack", "--json").stdout)[
        "verified_postings"
    ]
    output = cli("search", "stack", "--index", database).stdout
    assert "1. a.md | Stack | score=" in output


@pytest.mark.parametrize(
    "args",
    [
        ["search", "anything", "--index", "missing.sqlite3"],
        ["search", "anything", "--index", "missing.sqlite3", "--json"],
        ["build", "missing-directory", "--index", "any.sqlite3"],
    ],
)
def test_cli_errors(args):
    result = cli(*args)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "does not exist" in result.stderr
    if "--json" in args:
        assert "does not exist" in json.loads(result.stderr)["error"]


def test_cli_top_k_and_ranking_errors(corpus, database):
    assert cli("build", corpus, "--index", database).returncode == 0
    for options in [["--top-k", "0"], ["--k1", "nan"], ["--b", "2"]]:
        result = cli("search", "x", "--index", database, *options, "--json")
        assert result.returncode == 2
        assert "error" in json.loads(result.stderr)


def test_cli_unicode_paths_and_results(corpus, database):
    write_notes(corpus, {"東京-café.md": "# 東京 café\nStraße recursive function 東京"})
    assert cli("build", corpus, "--index", database, "--json").returncode == 0
    result = cli("search", "STRASSE 東京", "--index", database, "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hits"][0]["path"] == "東京-café.md"
    assert "Straße" in cli("search", "東京", "--index", database).stdout


def test_demo_deterministic_and_preserves_existing_files(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    assert cli("demo", first).returncode == cli("demo", second).returncode == 0
    snapshots = []
    for directory in (first, second):
        snapshots.append(
            {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        )
    assert snapshots[0] == snapshots[1]
    assert len(snapshots[0]) == 8
    result = cli("demo", first, "--json")
    assert result.returncode == 2
    assert "must be empty" in json.loads(result.stderr)["error"]


def test_benchmark_cli_real_small_run(tmp_path):
    pytest.importorskip("matplotlib")
    output = tmp_path / "bench"
    result = cli(
        "benchmark", "--out", output, "--sizes", 12, 24, "--repetitions", 2, "--warmup", 0, "--json"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["agreement"] is True
    summary = json.loads((output / "summary.json").read_text())
    assert [c["build"]["documents"] for c in summary["corpora"]] == [12, 24, 8]
    assert all(q["agreement"] for c in summary["corpora"] for q in c["queries"])
    assert (output / "raw.csv").is_file()
    assert (output / "latency-and-size.png").stat().st_size > 1000
    assert "preloaded" in (output / "report.md").read_text()
