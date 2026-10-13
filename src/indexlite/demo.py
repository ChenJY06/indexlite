import random
from pathlib import Path

from .models import IndexLiteError

NOTES = {
    "algorithms/recursion.md": """# Recursive functions and the call stack

A recursive function calls itself on a smaller problem. Each function call pushes
a stack frame containing arguments, local variables, and a return address.
The base case stops recursion. When the recursive call returns, its stack frame
is removed. An unbounded recursive function can exhaust the call stack.
For factorial, draw the stack for factorial(4) before tracing the return values.
""",
    "algorithms/complexity.md": """# Measuring algorithm cost

Binary search repeatedly halves a sorted array. Its comparison count grows
logarithmically. Linear search examines items in sequence and can visit the
whole array. Big O describes growth, while a benchmark measures a particular
implementation and machine. Report input size and repeated measurements.
""",
    "systems/memory.md": """# Stack and heap memory

Stack memory usually follows function call lifetimes. A heap allocation can
outlive the function that created it, so ownership and release need attention.
A dangling pointer refers to an object whose lifetime has ended. Memory safety
requires both valid addresses and valid object lifetimes.
""",
    "systems/processes.md": """# Processes and virtual memory

A process has its own virtual address space. The operating system schedules
threads and maps virtual pages to physical memory. A page fault may require
loading data from storage. Context switches and disk access affect latency.
Isolation helps prevent one process from corrupting another process's memory.
""",
    "data/queues.md": """# Queues and background jobs

A queue processes jobs in first-in first-out order. A background worker takes
a job, performs work, and records its outcome. Retries need idempotent handlers
because a failed acknowledgement can cause the same job to run twice.
A bounded queue applies backpressure when producers outrun consumers.
""",
    "data/search.md": """# Inverted indexes and ranking

An inverted index maps each term to documents containing it. A posting stores
a document identifier and term frequency. Search visits candidate documents
through postings. BM25 combines term frequency, document length, and inverse
document frequency. A common term usually distinguishes documents poorly.
""",
    "data/transactions.md": """# Durable transactions

A transaction groups storage changes so they commit together. A failed rebuild
should leave the previously published index usable. SQLite can store tables
and indexes in one database file. Parameterized SQL keeps values separate from
statements. Close readers before replacing a database file on Windows.
""",
    "text/unicode.txt": """Unicode text and normalization

Case-insensitive matching should handle Straße and STRASSE consistently.
Composed café and decomposed café can represent the same word. Compatibility
normalization also maps full-width characters such as ＡＢＣ to ABC. Hyphenated
words such as first-in are separate tokens. Numbers such as 2026 remain tokens.
""",
}


def fresh_directory(directory: str | Path) -> Path:
    directory = Path(directory).resolve()
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise IndexLiteError(f"output directory must be empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def generate_demo(directory: str | Path) -> dict:
    directory = fresh_directory(directory)
    for name, text in sorted(NOTES.items()):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(text)
    return dict(documents=len(NOTES), directory=str(directory))


def generate_synthetic(directory: str | Path, size: int, seed: int) -> dict:
    if size <= 0:
        raise IndexLiteError("synthetic corpus size must be positive")
    directory = fresh_directory(directory)
    rng = random.Random(seed)
    lengths = []
    for i in range(size):
        words = [f"doc{i:06d}"] + ["system"] * (1 + i % 5)
        words += [f"term{rng.randrange(256):03d}" for _ in range(rng.randint(32, 160))]
        if i % 5 == 0:
            words += ["memory"] * 2
        if i % 1000 == 0:
            words += ["quasar"] * 3
        rng.shuffle(words)
        lengths.append(len(words))
        shard = directory / f"{i // 1000:03d}"
        shard.mkdir(exist_ok=True)
        with (shard / f"doc{i:06d}.txt").open("x", encoding="utf-8", newline="\n") as file:
            file.write(" ".join(words) + "\n")
    return dict(
        documents=size,
        seed=seed,
        min_length=min(lengths),
        max_length=max(lengths),
        average_length=sum(lengths) / size,
        tokens=sum(lengths),
        vocabulary_filler=256,
        system_df=size,
        memory_df=(size + 4) // 5,
        quasar_df=(size + 999) // 1000,
    )
