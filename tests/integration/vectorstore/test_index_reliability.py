"""Fixed-size synthetic reliability probes; never touch configured user storage."""

import subprocess
import sys
from uuid import UUID, uuid4

import pytest
from chromadb.api.shared_system_client import SharedSystemClient

from ragdb.domain.models import Chunk
from ragdb.infrastructure.vectorstore import ChromaVectorStore


@pytest.mark.parametrize("count", [1, 3])
@pytest.mark.parametrize("individual", [False, True])
@pytest.mark.parametrize("repetition", range(3))
def test_tiny_indexes_query_after_close_and_process_reopen(tmp_path, count, individual, repetition):
    directory = tmp_path / "chroma"
    collections = [uuid4(), uuid4()]
    store = ChromaVectorStore(directory)
    try:
        for collection_id in collections:
            chunks = [Chunk(
                id=f"chunk-{n}", collection_id=collection_id, source_id=uuid4(),
                source_content_hash="a" * 64, generation=1, ordinal=n,
                text="synthetic", normalized_text="synthetic",
            ) for n in range(count)]
            batches = [[chunk] for chunk in chunks] if individual else [chunks]
            for batch in batches:
                store.upsert(batch, [[0.1, 0.2] for _ in batch])
            assert len(store.search(collection_id, [0.1, 0.2], count)) == count
    finally:
        store._client.close()
    reopened = ChromaVectorStore(directory)
    try:
        for collection_id in collections:
            assert len(reopened.search(collection_id, [0.1, 0.2], count)) == count
    finally:
        reopened._client.close()
    code = """
import sys
from pathlib import Path
from uuid import UUID
from ragdb.infrastructure.vectorstore import ChromaVectorStore
store = ChromaVectorStore(Path(sys.argv[1]))
try:
    for value in sys.argv[3:]:
        assert len(store.search(UUID(value), [0.1, 0.2], int(sys.argv[2]))) == int(sys.argv[2])
finally:
    store._client.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(directory), str(count), *map(str, collections)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_unclosed_adapters_accumulate_client_references(tmp_path):
    directory = tmp_path / "chroma"
    baseline = dict(SharedSystemClient._identifier_to_refcount)
    stores = [ChromaVectorStore(directory) for _ in range(12)]
    try:
        identifier = stores[0]._client._identifier
        # Chroma 1.5.9 owns both an application and an internal admin reference.
        assert SharedSystemClient._identifier_to_refcount[identifier] == 24
    finally:
        for store in stores:
            store._client.close()
    assert SharedSystemClient._identifier_to_refcount == baseline
