"""Fixed-size synthetic reliability probes; never touch configured user storage."""

import subprocess
import sys
from uuid import uuid4

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
        store.close()
    reopened = ChromaVectorStore(directory)
    try:
        for collection_id in collections:
            assert len(reopened.search(collection_id, [0.1, 0.2], count)) == count
    finally:
        reopened.close()
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
    store.close()
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
            store.close()
    assert SharedSystemClient._identifier_to_refcount == baseline


def test_close_is_idempotent_and_does_not_close_other_owner(tmp_path):
    from ragdb.domain.errors import StorageError

    baseline = dict(SharedSystemClient._identifier_to_refcount)
    first = ChromaVectorStore(tmp_path / "chroma")
    with ChromaVectorStore(tmp_path / "chroma") as second:
        first.close()
        first.close()
        assert second.search(uuid4(), [0.1, 0.2], 1) == []
        with pytest.raises(StorageError, match="已关闭"):
            first.search(uuid4(), [0.1, 0.2], 1)
    assert SharedSystemClient._identifier_to_refcount == baseline


def test_operation_scoped_clients_release_on_success_and_failure(tmp_path):
    from ragdb.domain.errors import StorageError

    baseline = dict(SharedSystemClient._identifier_to_refcount)
    store = ChromaVectorStore(tmp_path / "chroma", operation_scoped=True)
    assert not (tmp_path / "chroma").exists()
    for _ in range(12):
        assert store.search(uuid4(), [0.1, 0.2], 1) == []
        assert SharedSystemClient._identifier_to_refcount == baseline
        with pytest.raises(ValueError):
            store.search(uuid4(), [], 1)
        assert SharedSystemClient._identifier_to_refcount == baseline
    store.close()
    with pytest.raises(StorageError, match="已关闭"):
        store.search(uuid4(), [0.1, 0.2], 1)


def test_parallel_owners_release_without_interrupting_queries(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    baseline = dict(SharedSystemClient._identifier_to_refcount)
    barrier = Barrier(2)

    def run():
        with ChromaVectorStore(tmp_path / "chroma") as store:
            barrier.wait(timeout=10)
            for _ in range(6):
                assert store.search(uuid4(), [0.1, 0.2], 1) == []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run) for _ in range(2)]
        for future in futures:
            future.result(timeout=20)
    assert SharedSystemClient._identifier_to_refcount == baseline


def test_runtime_services_do_not_retain_vector_clients(tmp_path, monkeypatch):
    from ragdb.config import AppSettings, StorageSettings
    from ragdb.infrastructure.database import SQLiteDatabase
    from ragdb.runtime import ApplicationRuntime

    class Provider:
        def embed_texts(self, texts):
            return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr("ragdb.runtime.create_embedding_provider", lambda _: Provider())
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    runtime = ApplicationRuntime(AppSettings(storage=StorageSettings(data_dir=tmp_path)), database)
    baseline = dict(SharedSystemClient._identifier_to_refcount)
    for _ in range(12):
        assert runtime.collection_service().list_all() == []
        assert runtime.search_service().search(uuid4(), "synthetic") == []
        assert SharedSystemClient._identifier_to_refcount == baseline
