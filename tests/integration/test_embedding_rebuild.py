from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from ragdb.application.embedding_rebuild import EmbeddingRebuildCancelled, EmbeddingRebuildService
from ragdb.config import EmbeddingSettings
from ragdb.domain.enums import SourceStatus, SourceType
from ragdb.domain.errors import StorageError
from ragdb.domain.models import Chunk, Collection, Source
from ragdb.infrastructure.database import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteDatabase,
    SQLiteEmbeddingOperationGate,
    SQLiteEmbeddingProfileRepository,
    SQLiteSourceRepository,
    SQLiteKeywordIndex,
)
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.vectorstore import ChromaVectorStore


class FakeEmbeddingProvider:
    provider_name = "cloud"
    model_name = "test-embedding"

    def __init__(self, fail_on_call=None):
        self.calls = 0
        self.fail_on_call = fail_on_call

    def embed_texts(self, texts):
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("simulated embedding failure")
        return [[float(index + 1) / 10 for index in range(3)] for _ in texts]


def make_chunk(collection_id, source_id, text, ordinal=0):
    return Chunk(
        id=f"{source_id}-{ordinal}", collection_id=collection_id, source_id=source_id,
        source_content_hash="a" * 64, generation=1, ordinal=ordinal,
        text=text, normalized_text=text.casefold(),
    )


def setup_database(path: Path):
    database = SQLiteDatabase(path / "ragdb.sqlite3")
    database.initialize()
    collection_repo = SQLiteCollectionRepository(database)
    source_repo = SQLiteSourceRepository(database)
    chunk_repo = SQLiteChunkRepository(database)
    collections = [
        Collection(name="知识库 A"),
        Collection(name="知识库 B"),
        Collection(name="知识库 C"),
        Collection(name="知识库 D"),
    ]
    sources = []
    chunks = []
    source_types = [SourceType.WEB, SourceType.GITHUB_REPOSITORY, SourceType.MANUAL_TEXT, SourceType.TEXT]
    for collection in collections:
        collection_repo.create(collection)
        source = Source(
            collection_id=collection.id,
            source_type=source_types[len(sources)],
            title=f"资料 {len(sources)}",
            uri=f"manual://{len(sources)}",
            content_hash="a" * 64,
            status=SourceStatus.READY,
            embedding_provider="local",
            embedding_model="BAAI/bge-small-zh-v1.5",
            current_generation=1,
        )
        source_repo.create(source)
        sources.append(source)
        chunks.extend([make_chunk(collection.id, source.id, f"文本 {len(sources)}-{n}", n) for n in range(2)])
    chunk_repo.add_many(chunks)
    SQLiteKeywordIndex(database).index(chunks)
    old_vectors = [[0.1, 0.2] for _ in chunks]
    legacy_store = ChromaVectorStore(path / "chroma")
    legacy_store.upsert(chunks, old_vectors)
    old_settings = EmbeddingSettings()
    SQLiteEmbeddingProfileRepository(database).initialize(old_settings)
    return database, collections, sources, chunks, legacy_store, old_settings


def test_rebuild_switches_all_source_types_after_complete_verification(tmp_path, monkeypatch) -> None:
    database, collections, sources, chunks, old_store, _ = setup_database(tmp_path)
    provider = FakeEmbeddingProvider()
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: provider)
    service = EmbeddingRebuildService(database, tmp_path / "chroma", batch_size=1)
    progress = []
    settings = EmbeddingSettings(provider="cloud", cloud_model="test-embedding")
    with database.connect() as connection:
        before_fts = list(map(tuple, connection.execute("SELECT * FROM chunks_fts")))
    stale = chunks[0].model_copy(update={"id": "stale-chunk", "generation": 2})
    SQLiteChunkRepository(database).add_many([stale])

    result = service.rebuild(settings, on_progress=progress.append)

    fingerprint = embedding_profile_fingerprint(settings)
    active, active_fingerprint, namespace = SQLiteEmbeddingProfileRepository(database).get()
    new_store = ChromaVectorStore(tmp_path / "chroma", fingerprint)
    assert result.chunk_count == len(chunks)
    assert result.collection_count == len(collections)
    assert active == settings and active_fingerprint == fingerprint and namespace == fingerprint
    assert all(new_store.has_chunks(chunk.collection_id, [chunk.id]) for chunk in chunks)
    assert all(old_store.has_chunks(chunk.collection_id, [chunk.id]) for chunk in chunks)
    assert [item.source_type for item in SQLiteSourceRepository(database).list_for_collection(collections[0].id)] == [SourceType.WEB]
    assert progress[-1].completed_chunks == len(chunks)
    assert {source.embedding_provider for collection in collections for source in SQLiteSourceRepository(database).list_for_collection(collection.id)} == {"cloud"}
    assert not new_store.has_chunks(stale.collection_id, [stale.id])
    with database.connect() as connection:
        assert list(map(tuple, connection.execute("SELECT * FROM chunks_fts"))) == before_fts
    from ragdb.application.search import SearchService
    search = SearchService(provider, new_store, SQLiteKeywordIndex(database), SQLiteSourceRepository(database))
    assert search.search(collections[0].id, "文本")


def test_cancelled_rebuild_keeps_old_profile_and_index(tmp_path, monkeypatch) -> None:
    database, collections, _, chunks, old_store, old_settings = setup_database(tmp_path)
    provider = FakeEmbeddingProvider()
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: provider)
    service = EmbeddingRebuildService(database, tmp_path / "chroma", batch_size=1)
    settings = EmbeddingSettings(provider="cloud", cloud_model="test-embedding")

    with pytest.raises(EmbeddingRebuildCancelled):
        service.rebuild(settings, should_cancel=lambda: True)

    assert SQLiteEmbeddingProfileRepository(database).get()[0] == old_settings
    assert all(old_store.has_chunks(chunk.collection_id, [chunk.id]) for chunk in chunks)
    assert not ChromaVectorStore(tmp_path / "chroma", embedding_profile_fingerprint(settings)).has_chunks(
        collections[0].id, [chunks[0].id]
    )


def test_failed_rebuild_cleans_staging_and_preserves_old_profile(tmp_path, monkeypatch) -> None:
    database, collections, _, chunks, old_store, old_settings = setup_database(tmp_path)
    # The first call validates the endpoint; the third call fails after one chunk was staged.
    provider = FakeEmbeddingProvider(fail_on_call=3)
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: provider)
    service = EmbeddingRebuildService(database, tmp_path / "chroma", batch_size=1)
    settings = EmbeddingSettings(provider="cloud", cloud_model="test-embedding")

    with pytest.raises(RuntimeError, match="simulated embedding failure"):
        service.rebuild(settings)

    assert SQLiteEmbeddingProfileRepository(database).get()[0] == old_settings
    assert all(old_store.has_chunks(chunk.collection_id, [chunk.id]) for chunk in chunks)
    assert not ChromaVectorStore(tmp_path / "chroma", embedding_profile_fingerprint(settings)).has_chunks(
        collections[0].id, [chunks[0].id]
    )


def test_rebuild_gate_blocks_ingestion_and_ingestion_blocks_rebuild(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    gate = SQLiteEmbeddingOperationGate(database)

    with gate.ingestion():
        with pytest.raises(StorageError, match="正在导入"):
            with gate.rebuild():
                pass
    with gate.rebuild():
        with pytest.raises(StorageError, match="全局重建"):
            with gate.ingestion():
                pass


def test_dead_rebuild_owner_is_recovered(tmp_path):
    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "UPDATE embedding_operation_gate SET rebuild_active = 1, rebuild_owner_pid = 2147483647"
        )

    with SQLiteEmbeddingOperationGate(database).ingestion():
        pass

    with database.connect() as connection:
        assert connection.execute("SELECT rebuild_active FROM embedding_operation_gate").fetchone()[0] == 0


@pytest.mark.parametrize("fault", ["write", "verify", "publish"])
def test_storage_faults_preserve_searchable_old_index(tmp_path, monkeypatch, fault):
    database, collections, sources, chunks, old_store, old_settings = setup_database(tmp_path)
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: FakeEmbeddingProvider())
    service = EmbeddingRebuildService(database, tmp_path / "chroma", batch_size=1)
    settings = EmbeddingSettings(provider="cloud", cloud_model="test-embedding")
    if fault == "write":
        def fail_write(*args):
            raise StorageError("write fault")
        monkeypatch.setattr(ChromaVectorStore, "upsert", fail_write)
    elif fault == "verify":
        monkeypatch.setattr(ChromaVectorStore, "has_chunks", lambda *args: False)
    else:
        # Fail AFTER the profile update inside the publishing transaction.
        with database.connect() as connection:
            connection.execute("CREATE TRIGGER fail_publish BEFORE UPDATE OF embedding_model ON sources "
                               "BEGIN SELECT RAISE(ABORT, 'publish fault'); END")
    with pytest.raises((StorageError, sqlite3.Error)):
        service.rebuild(settings)
    assert SQLiteEmbeddingProfileRepository(database).get() == (
        old_settings, embedding_profile_fingerprint(old_settings), "legacy"
    )
    assert SQLiteSourceRepository(database).get(sources[0].id).embedding_model == old_settings.local_model
    assert old_store.search(collections[0].id, [0.1, 0.2], 10)
    target = ChromaVectorStore(tmp_path / "chroma", embedding_profile_fingerprint(settings))
    assert target.search(collections[0].id, [0.1, 0.2, 0.3], 10) == []
    with SQLiteEmbeddingOperationGate(database).ingestion():
        pass


def test_cancel_at_last_progress_does_not_publish(tmp_path, monkeypatch):
    database, collections, _, chunks, old_store, old_settings = setup_database(tmp_path)
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: FakeEmbeddingProvider())
    progress = []
    with pytest.raises(EmbeddingRebuildCancelled):
        EmbeddingRebuildService(database, tmp_path / "chroma").rebuild(
            EmbeddingSettings(local_model="replacement"), on_progress=progress.append,
            should_cancel=lambda: bool(progress and progress[-1].completed_chunks == len(chunks)),
        )
    assert SQLiteEmbeddingProfileRepository(database).get()[0] == old_settings
    assert old_store.search(collections[0].id, [0.1, 0.2], 10)


def test_process_probe_does_not_signal_live_process():
    # A child protects the test runner from regression to os.kill(pid, 0) on Windows.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert SQLiteEmbeddingOperationGate._process_is_alive(child.pid)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_interrupted_staging_is_cleaned_on_retry(tmp_path, monkeypatch):
    database, collections, _, chunks, _, _ = setup_database(tmp_path)
    settings = EmbeddingSettings(local_model="replacement")
    target = ChromaVectorStore(tmp_path / "chroma", embedding_profile_fingerprint(settings))
    target.upsert([chunks[0].model_copy(update={"id": "orphan"})], [[0.1, 0.2, 0.3]])
    with database.connect() as connection:
        connection.execute("UPDATE embedding_operation_gate SET rebuild_active = 1, rebuild_owner_pid = 2147483647")
        connection.execute("INSERT INTO embedding_ingestion_leases VALUES ('dead-import', 2147483647, '2026-09-24')")
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: FakeEmbeddingProvider())
    result = EmbeddingRebuildService(database, tmp_path / "chroma").rebuild(settings)
    assert result.changed
    assert not target.has_chunks(collections[0].id, ["orphan"])
    assert target.has_chunks(collections[0].id, [chunks[0].id])


def test_runtime_services_block_during_rebuild_and_reject_stale_writes(tmp_path, monkeypatch):
    from ragdb.config import AppSettings, StorageSettings
    from ragdb.runtime import ApplicationRuntime
    database, collections, sources, _, _, _ = setup_database(tmp_path)
    monkeypatch.setattr("ragdb.runtime.create_embedding_provider", lambda _: FakeEmbeddingProvider())
    runtime = ApplicationRuntime(AppSettings(storage=StorageSettings(data_dir=tmp_path)), database, tmp_path / "config.toml")
    ingestion = runtime.ingestion_service()
    deletion = runtime.source_service()
    collection_service = runtime.collection_service()
    stale_search = runtime.search_service()
    with SQLiteEmbeddingOperationGate(database).rebuild():
        with pytest.raises(StorageError, match="全局重建"):
            ingestion.ingest_text(collections[0], "new text")
        with pytest.raises(StorageError, match="全局重建"):
            deletion.delete(sources[0].id)
        with pytest.raises(StorageError, match="全局重建"):
            collection_service.delete_by_name(collections[0].name)
    candidate = EmbeddingSettings(local_model="changed")
    SQLiteEmbeddingProfileRepository(database).activate(candidate, embedding_profile_fingerprint(candidate))
    with pytest.raises(StorageError, match="已切换"):
        ingestion.ingest_text(collections[0], "new text")
    with pytest.raises(StorageError, match="已切换"):
        stale_search.search(collections[0].id, "文本")
    with pytest.raises(StorageError, match="已切换"):
        deletion.delete(sources[0].id)
    assert runtime.ingestion_service().operation_gate.expected_profile[0] == embedding_profile_fingerprint(candidate)


def test_empty_database_validates_before_switch(tmp_path, monkeypatch):
    database = SQLiteDatabase(tmp_path / "empty.sqlite3")
    database.initialize()
    SQLiteEmbeddingProfileRepository(database).initialize(EmbeddingSettings())
    provider = FakeEmbeddingProvider()
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: provider)
    result = EmbeddingRebuildService(database, tmp_path / "chroma").rebuild(EmbeddingSettings(local_model="new"))
    assert result.changed and result.chunk_count == 0 and provider.calls == 1


def test_published_profile_recovers_after_toml_sync_failure(tmp_path, monkeypatch):
    from ragdb.application.model_settings import ModelSettingsService
    from ragdb.config import AppSettings, StorageSettings, load_settings
    from ragdb.runtime import ApplicationRuntime
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    config = tmp_path / "config.toml"
    config.write_text(f"[storage]\ndata_dir = '{tmp_path.as_posix()}'\n", encoding="utf-8")
    runtime = ApplicationRuntime(AppSettings(storage=StorageSettings(data_dir=tmp_path)), database, config)
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: FakeEmbeddingProvider())
    candidate = EmbeddingSettings(local_model="replacement")
    with monkeypatch.context() as patcher:
        def unavailable(*args):
            raise OSError("disk unavailable")
        patcher.setattr(ModelSettingsService, "persist_embedding", unavailable)
        result = runtime.rebuild_embeddings(candidate)
    assert result.changed and result.configuration_warning
    assert load_settings(config).embedding.local_model != "replacement"
    restarted = ApplicationRuntime.from_config(config)
    assert restarted.settings.embedding.local_model == "replacement"
    assert load_settings(config).embedding.local_model == "replacement"


def test_rebuild_gate_blocks_another_process(tmp_path):
    path = tmp_path / "db.sqlite3"
    database = SQLiteDatabase(path)
    database.initialize()
    code = (
        "from pathlib import Path\n"
        "import sys\n"
        "from ragdb.infrastructure.database import SQLiteDatabase, SQLiteEmbeddingOperationGate\n"
        "with SQLiteEmbeddingOperationGate(SQLiteDatabase(Path(sys.argv[1]))).ingestion():\n"
        "    print('unexpected ingestion')\n"
    )
    with SQLiteEmbeddingOperationGate(database).rebuild():
        result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, timeout=15)
    assert result.returncode != 0
    assert b"StorageError" in result.stderr
    assert b"unexpected ingestion" not in result.stdout


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
def test_rebuild_releases_its_client_on_every_exit(tmp_path, monkeypatch, outcome):
    from chromadb.api.shared_system_client import SharedSystemClient

    database, collections, _, _, old_store, _ = setup_database(tmp_path)
    baseline = dict(SharedSystemClient._identifier_to_refcount)
    provider = FakeEmbeddingProvider(fail_on_call=3 if outcome == "failure" else None)
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: provider)
    service = EmbeddingRebuildService(database, tmp_path / "chroma", batch_size=1)
    progress = []
    def rebuild():
        return service.rebuild(
            EmbeddingSettings(local_model="replacement"), on_progress=progress.append,
            should_cancel=lambda: outcome == "cancel" and bool(progress and progress[-1].completed_chunks),
        )
    try:
        if outcome == "success":
            assert rebuild().changed
        else:
            with pytest.raises(RuntimeError):
                rebuild()
        assert SharedSystemClient._identifier_to_refcount == baseline
        assert old_store.search(collections[0].id, [0.1, 0.2], 1)
    finally:
        old_store.close()
