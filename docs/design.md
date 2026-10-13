# Design

IndexLite is a local, single-writer document index. SQLite persists ordinary
tables; Python implements tokenization, postings construction, candidate
selection, BM25, and top-k. Search uses neither SQLite FTS nor `LIKE`.

## Ingestion and tokenization

The builder reads paths recursively in ascending, case-sensitive Unicode order
of relative POSIX paths. IDs start at 1 in that order, so smaller IDs also mean
lexicographically earlier paths. Symlinks and unsupported extensions are skipped
and reported. UTF-8 (with an optional BOM) is required for `.txt` and `.md`.
Markdown is treated as text: markup punctuation separates tokens. Text-bearing
PDFs use optional `pypdf` extraction. Encrypted PDFs requiring a password, broken
PDFs, and PDFs without extractable text produce explicit errors. OCR is outside
version one. The title is the first nonempty line, with leading Markdown heading
markers removed, limited to 120 characters.

One tokenizer serves documents and queries:

1. Apply Unicode NFKC compatibility normalization.
2. Apply `casefold()` for case-insensitive matching.
3. Apply NFC to compose equivalent sequences after case folding.
4. Extract runs matching Python's Unicode regex `[^\W_]+`.

Tokens contain Unicode alphanumeric characters, excluding underscores.
Punctuation, apostrophes, underscores, and hyphens separate words: `first-in`
becomes `first`, `in`; `isn't` becomes `isn`, `t`; `C++` becomes `c`. Numbers
are retained; `3.14` becomes `3`, `14`. Contiguous scripts such as Chinese are
one token per contiguous run, not linguistically segmented. `Straße` and
`STRASSE` match, as do composed and decomposed `café`. Remaining combining
marks that cannot compose act as separators. There is no stemming or stop-word
removal. Tokenization uses Python's Unicode tables; the benchmark records the
Python version. Rebuild after a runtime upgrade if exact Unicode reproducibility
is required.

Queries use sorted, unique tokens. Repetition does not boost a term; input without
tokens matches nothing. The default is OR: any term can match. Unknown terms add
no scores. Only nonempty documents enter the corpus, so skipped empty documents
affect neither N nor average length.

## Storage

The schema lives in `src/indexlite/storage.py`:

| Table | Contents and lookup structure |
|---|---|
| `documents` | Integer ID, unique relative path, title, extracted text, token length, original file bytes |
| `terms` | Integer ID, unique token, document frequency `df` |
| `postings` | `(term_id, document_id)` primary key and positive term frequency `tf`; `WITHOUT ROWID` |
| `metadata` | JSON values keyed by name: schema, tokenizer, ranking settings, corpus totals |

Unique term and path constraints create B-tree lookup indexes. The postings
primary key supports lookup by term. `postings_by_document` supports validation
and reverse access. Foreign keys connect postings to terms and documents;
positive-frequency and length constraints prevent invalid builder output.
All user values use SQL parameters.

The builder retains a term-to-ID dictionary and document-frequency counters.
Only the current document's text and frequency counter are needed for ingestion,
alongside the vocabulary and the sorted file-path list. It inserts that
document's postings, then persists all frequencies and metadata in one explicit
`BEGIN IMMEDIATE` / commit transaction. This is a complete rebuild, not an
incremental update.

`PRAGMA user_version` and metadata both identify schema version 1. Tokenizer
configuration and default `k1`/`b` are stored with corpus size, total tokens,
average length, terms, postings, and indexed source bytes. Schema version 1
defines the scoring variant and query policy described below. Search opens an
existing file using `mode=ro`, enables `query_only`, and begins a read transaction
to retain one snapshot. Missing files are never silently created.

Opening validates versions, configuration, scalar statistics, JSON, and required
columns. It does not traverse every document. Build validation and `verify` do
full SQLite integrity and foreign-key checks, recount statistics, and check
posting sums and document frequencies. `verify` also retokenizes stored text and
compares every document's postings before comparing query results. Subtle data
corruption outside queried pages may therefore require `verify` to detect.

## BM25

For document d and the set of unique query terms Q:

```text
score(d, Q) = sum over t in Q present in d:
    idf(t) * tf(t,d) * (k1 + 1)
    / [tf(t,d) + k1 * (1 - b + b * length(d) / avgdl)]

idf(t) = log(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
```

`log` is the natural logarithm. `N` is the number of nonempty indexed documents;
`df(t)` counts documents containing t; `tf(t,d)` counts t's occurrences in d;
`length(d)` is d's token count; `avgdl` is total tokens divided by N. The
nonnegative IDF variant is evaluated with `math.log1p`. Defaults are `k1=1.2`
and `b=0.75`. `k1` must be finite and positive; `b` must be finite and in [0,1].
Search can override either value without changing the stored defaults. Empty
corpora return no matches without division by zero.

Search resolves each query term through the term index, reads its postings with
document lengths, and accumulates scores in a dictionary keyed by document ID.
The candidate set is the union of query postings. It never scans all document
texts for an indexed query. A ubiquitous query term can still make every
document a candidate.

## Top-k and excerpts

A bounded min-heap holds `(score, -document_id)`: the root is the worst retained
hit. A better candidate replaces it. The final heap is sorted by descending
score, then ascending ID. This provides deterministic path-based ties within an
index. If C candidates match, scoring visits the relevant postings, selection
costs O(C log k), and its heap uses O(k) memory; the score dictionary uses O(C).
For k greater than C, all matches are returned. k must be positive.

Only selected hits fetch stored text. Excerpts use original character offsets
and shared token normalization to locate query occurrences, then choose a short
window near a dense group of matches. Whitespace is collapsed and truncation is
marked with an ellipsis. Excerpt generation traverses the selected texts; a
very long document can make formatting noticeably expensive. The benchmark
reports it separately from scoring.

## Rebuild publication and failures

The output index must be outside the source directory. The builder never writes
source files. A temporary SQLite file is created beside the destination, ensuring
publication stays on the same filesystem. It uses rollback journaling and
`synchronous=FULL`. After commit and close, validation opens the temporary file
read-only. Only successful validation permits `os.replace` to publish it.
Errors close and remove the temporary file; the previous destination stays intact.

Extraction errors abort by default. `--skip-errors` deliberately publishes a
reduced corpus while returning each skipped error in the build report.
Unsupported files and tokenless text files are always reported and skipped.

On Windows, an open SQLite reader can prevent replacement. IndexLite reports
that readers must close, preserves the old database, and removes the temporary
one. It does not delete the old index, retry indefinitely, or fall back to a
non-atomic copy. Close readers and rerun the build. On systems permitting atomic
replacement of open files, existing readers keep their old snapshot; new readers
open the new index. Tests exercise both platform behaviours.

Version one requires the caller to serialize rebuilds. Two simultaneous builders
are unsupported and can race to publish. Database transactions and rename provide
process-failure safety; filesystem rename durability after a power failure is
platform dependent and is not guaranteed by this project. No directory fsync or
cross-process writer lock is implemented.

## Useful next steps

Incremental updates with content hashes, phrase queries with positional postings,
and compressed postings are possible extensions. Each would need its own storage
version, correctness tests, and performance experiments. They are intentionally
outside the current implementation.
