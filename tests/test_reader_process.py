import os
import subprocess
import sys

import pytest

from indexlite.builder import build_index
from indexlite.models import IndexLiteError
from indexlite.search import search
from indexlite.storage import Index

from .conftest import write_notes


def test_rebuild_while_another_process_reads(corpus, database):
    write_notes(corpus, {"a.txt": "old snapshot"})
    build_index(corpus, database)
    script = """
import sys
from indexlite.storage import Index
from indexlite.search import search
with Index(sys.argv[1]) as index:
    print('ready', flush=True)
    sys.stdin.readline()
    print(search(index, 'old').hits[0].path, flush=True)
"""
    reader = subprocess.Popen(
        [sys.executable, "-c", script, str(database)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert reader.stdout.readline().strip() == "ready"
        write_notes(corpus, {"a.txt": "new snapshot"})
        if os.name == "nt":
            with pytest.raises(IndexLiteError, match="close processes"):
                build_index(corpus, database)
        else:
            build_index(corpus, database)
        output, errors = reader.communicate("release\n", timeout=10)
        assert reader.returncode == 0, errors
        assert output.strip() == "a.txt"
    finally:
        if reader.poll() is None:
            reader.kill()
        reader.communicate(timeout=10)
    build_index(corpus, database)
    with Index(database) as index:
        assert search(index, "new").hits[0].path == "a.txt"
