import csv

import pytest

from indexlite.benchmark import p95, run_benchmarks
from indexlite.demo import generate_synthetic
from indexlite.models import IndexLiteError


def test_percentile_nearest_rank():
    assert p95(list(range(1, 21))) == 19
    assert p95([4, 1, 3, 2]) == 4


def test_synthetic_determinism_and_distinctness(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    first = generate_synthetic(a, 50, 1729)
    assert first == generate_synthetic(b, 50, 1729)
    contents = [path.read_text() for path in sorted(a.rglob("*.txt"))]
    assert contents == [path.read_text() for path in sorted(b.rglob("*.txt"))]
    assert len(set(contents)) == 50
    assert first["system_df"] == 50
    assert first["memory_df"] == 10
    assert first["quasar_df"] == 1
    assert sum("quasar" in text.split() for text in contents) == 1
    assert min(len(text.split()) for text in contents) < max(len(text.split()) for text in contents)


@pytest.mark.parametrize("sizes", [[], [0], [-1], [5, 5]])
def test_invalid_benchmark_sizes(tmp_path, sizes):
    with pytest.raises(IndexLiteError, match="distinct positive"):
        run_benchmarks(tmp_path / "out", sizes)


def test_raw_csv_consistent(tmp_path):
    pytest.importorskip("matplotlib")
    output = tmp_path / "run"
    run_benchmarks(output, [10], repetitions=2, warmup=0)
    with (output / "raw.csv").open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2 * (8 + 6)
    assert all(row["agreement"] == "True" for row in rows)
    assert {row["order"] for row in rows} == {"indexed-first", "reference-first"}
