# Benchmark methodology

Run the same experiment locally:

```sh
python -m pip install -e '.[dev,bench]'
indexlite benchmark --out artifacts/benchmark-new --sizes 1000 10000 50000 \
  --seed 1729 --repetitions 20 --warmup 3 --top-k 10
```

In PowerShell, put the command on one line. `--out` must be an empty directory.
Generation never deletes an existing corpus. Sizes, seed, repetitions, warm-up
count, and top-k are configurable. The experiment includes the eight original
demo notes separately.

## Corpus and queries

Each synthetic UTF-8 document has a unique `docNNNNNN` token, preventing identical
documents. A local `random.Random(seed)` generates 32–160 filler tokens from a
256-term vocabulary and shuffles each document. Special frequencies are:

| Term | Term frequency | Document frequency |
|---|---|---|
| `docNNNNNN` | 1 | 1 |
| `system` | 1–5, according to document ID modulo 5 | N |
| `memory` | 2, every fifth document | ceil(N/5) |
| `quasar` | 3, every thousandth document | ceil(N/1000) |
| `term000` through `term255` | Random, with replacement | Measured from the generated corpus |

Lengths vary; the saved summary records exact token totals, minimum, maximum,
and mean. Each requested size restarts the same seed, so larger corpora contain
the smaller corpora as prefixes. Files are sharded into directories of up to
1,000 documents. Generation time is outside index-build time.

Synthetic queries, in execution order:
`quasar`, `system`, `memory`, `quasar memory`, `term000 term001`, `doc000000`,
`missingtoken`, `system quasar`. These cover rare terms, a term present in every
document, moderately common terms, OR combinations, a singleton, and an absent
term. The absent-term case is especially favourable to an index and should not
be treated as a typical query.

Demo queries are `recursive function stack`, `memory`, `queue`, `unicode`, `the`,
and `missingtoken`. This corpus is too small for broad performance conclusions;
it illustrates fixed overhead and produces readable search results. These
queries and corpora are experiments, not samples of real user traffic.

## Boundaries and comparison

The build timer starts before traversal and ends after publication. It includes
all reads and validation. Reports separate extraction/read+stat time,
tokenization+frequency counting, SQLite construction+commit, validation, and
publication. Total also contains path traversal/sorting, schema setup, and small
bookkeeping overhead. Indexed source bytes count successfully indexed files;
index bytes count the published SQLite file, including stored extracted text
and B-tree indexes.

Opening a read-only index is measured separately. First-query measurements use
one newly opened connection for each query immediately after a build. The OS
page cache is not flushed, and a fresh connection does not imply a cold cache.
Their exact opening, scoring, and formatting timings are saved in summary JSON.

Warm measurements use one connection. Before timing samples, every query's
candidate count, ordered document IDs, and scores are checked against the
exhaustive reference; a disagreement aborts the run. Three unrecorded warm-up
passes precede 20 recorded repetitions. Indexed/reference execution order
alternates across repetitions and queries. Agreement is also checked after every
timed pair. Scores use relative/absolute tolerance 1e-12; order must match exactly.

The indexed scoring timer includes query tokenization, SQL lookups and posting
reads, Python BM25, score accumulation, and heap top-k. Formatting time includes
fetching selected text and excerpt generation. An additional timer captures the
total Python `search` call. CLI startup and printing/JSON serialization are
excluded from these in-process query measurements; first-query opening is
reported separately.

The exhaustive reference preloads all stored texts into token-frequency
dictionaries and independently derives lengths and document frequencies.
Preloading is timed separately, then excluded from warm-query latency. Each
query visits every document's dictionary and fully sorts matching scores. It
uses the same tokenizer and BM25 contribution function, OR semantics, unique
query terms, and ID tie-breaking. Hand-calculated BM25 tests supply independent
formula verification; agreement alone could miss a shared scoring bug.

Scoring speedup is reference median divided by indexed scoring median. This is a
comparison of candidate selection and ranking after reference preloading, not
an end-to-end claim including disk reads, reference setup, snippets, or process
startup. It exposes a useful disadvantage too: a common-term reference query
can be faster because its dictionaries are already in memory, while the indexed
path still crosses the Python/SQLite boundary for each posting. Both approaches
must score every match. Formatting can exceed scoring for selective queries.

Medians use `statistics.median`; p95 uses the nearest-rank sample at
`ceil(0.95 * repetitions)`. With 20 samples, tail estimates are coarse. There is
no controlled cache eviction, isolated-core scheduling, or production load.
The run records OS, CPU identifier, logical CPU count, Python/SQLite versions,
package versions, settings, characteristics, and full per-query measurements.
No memory measurement is reported: Python allocation tracking would not measure
total process RAM or SQLite's native allocations.

## Output and recorded results

Each run writes `raw.csv` with every warm sample, `summary.json` with aggregates
and first-query measurements, `report.md`, and `latency-and-size.png`. Generated
corpora, databases, and raw output stay under ignored `artifacts/`. The compact
checked-in results contain the aggregate JSON, report, and plot; raw measurements
remain in the local run directory and can be reproduced with the command above.

The [13 October 2026 report](results/2026-10-13/report.md),
[aggregate JSON](results/2026-10-13/summary.json), and
[plot](results/2026-10-13/latency-and-size.png) contain actual measurements.
The aggregate JSON identifies the raw CSV by SHA-256 and records 600 warm samples.
The local raw data lives at `artifacts/benchmark-final-2026-10-13/raw.csv`.
The 1,000-document case was measured in a separate run after the main run; all
cases used the same settings. Measurements ran on the host Windows environment,
with background scheduling and filesystem/cache conditions uncontrolled.
At 50,000 documents, extraction/read+stat accounted for 607.841 of the 689.640
build seconds, so throughput should not be generalized to other storage systems.

Agreement tests execution consistency; relevance is supported only by small
hand-designed ranking tests and readable demo results, not a judged relevance
dataset.
