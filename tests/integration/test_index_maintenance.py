from uuid import uuid4

import pytest

from ragdb.application.index_maintenance import IndexMaintenanceService
from ragdb.config import EmbeddingSettings
from ragdb.domain.errors import ConflictError, StorageError
from ragdb.domain.models import Collection
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteCollectionRepository, SQLiteEmbeddingProfileRepository, SQLiteEmbeddingOperationGate, SQLiteOperationLogRepository
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.vectorstore import ChromaVectorStore


@pytest.fixture(autouse=True)
def release_test_chroma_systems():
    # The legacy vector store has no close API. Release only systems created by
    # this test so many isolated HNSW databases do not exhaust Windows handles.
    from chromadb.api.shared_system_client import SharedSystemClient
    existing = set(SharedSystemClient._identifier_to_system)
    yield
    for key in set(SharedSystemClient._identifier_to_system) - existing:
        SharedSystemClient._identifier_to_system.pop(key).stop()
        SharedSystemClient._identifier_to_refcount.pop(key, None)


@pytest.fixture
def indexed(tmp_path):
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    collections = [SQLiteCollectionRepository(database).create(Collection(name=name)) for name in ("资料 A", "资料 B")]
    candidate = EmbeddingSettings(provider="ollama")
    fingerprint = embedding_profile_fingerprint(candidate)
    SQLiteEmbeddingProfileRepository(database).activate(candidate, fingerprint)
    service = IndexMaintenanceService(database, tmp_path / "chroma")
    client = ChromaVectorStore(tmp_path / "chroma")._client
    for collection in collections:
        for namespace in ("legacy", fingerprint, "b" * 64):
            stored = client.create_collection(
                name=ChromaVectorStore.collection_name(collection.id, namespace),
                metadata={"ragdb_collection_id": str(collection.id)}, embedding_function=None,
                configuration={"hnsw": {"batch_size": 3, "sync_threshold": 3}},
            )
            # Keep these tiny historical-index fixtures durably materialized.
            stored.add(ids=["one", "other-a", "other-b"],
                       embeddings=[[0.1, 0.2], [0.8, 0.1], [0.9, 0.2]],
                       documents=["synthetic", "second", "third"])
            import time
            from chromadb.errors import InternalError
            deadline = time.monotonic() + 5
            while True:
                try:
                    assert stored.query(query_embeddings=[[0.1, 0.2]], n_results=1)["ids"] == [["one"]]
                    break
                except InternalError as exc:
                    if "Nothing found on disk" not in str(exc) or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
    return service, client, collections, fingerprint


def test_preview_classifies_existing_indexes_without_mutation(indexed):
    service, client, collections, fingerprint = indexed
    unknown = [
        ("foreign_collection", {"ragdb_collection_id": str(collections[0].id)}),
        (ChromaVectorStore.collection_name(uuid4(), "c" * 64), {"other": "metadata"}),
        (ChromaVectorStore.collection_name(collections[0].id, "d" * 64), None),
        (ChromaVectorStore.collection_name(collections[0].id, "e" * 64), {"ragdb_collection_id": str(uuid4())}),
    ]
    for name, metadata in unknown:
        client.create_collection(name=name, metadata=metadata, embedding_function=None)
    before = {item.name: (str(item.id), item.count()) for item in client.list_collections()}

    result = service.preview()

    assert len(result.candidates) == 4
    assert len([item for item in result.items if item.state == "active"]) == 2
    assert len([item for item in result.items if item.state == "unknown"]) == 4
    assert result.active_fingerprint == fingerprint
    assert result.preview_id == service.preview().preview_id
    assert before == {item.name: (str(item.id), item.count()) for item in client.list_collections()}


def test_preview_identity_changes_when_same_name_is_recreated(indexed):
    service, client, _, _ = indexed
    before = service.preview()
    target = before.candidates[0]
    client.delete_collection(target.name)
    client.create_collection(name=target.name, metadata={"ragdb_collection_id": str(target.collection_id)}, embedding_function=None)
    assert service.preview().preview_id != before.preview_id


def test_preview_handles_active_legacy_and_empty_storage(tmp_path):
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    SQLiteEmbeddingProfileRepository(database).initialize(EmbeddingSettings())
    service = IndexMaintenanceService(database, tmp_path / "missing-chroma")
    assert not service.preview().items
    assert not (tmp_path / "missing-chroma").exists()
    collection = SQLiteCollectionRepository(database).create(Collection(name="legacy"))
    client = ChromaVectorStore(service.chroma_directory)._client
    client.create_collection(name=ChromaVectorStore.collection_name(collection.id), embedding_function=None)
    result = service.preview()
    assert result.items[0].state == "active"
    assert not result.candidates


def test_preview_requires_known_active_profile(tmp_path):
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    with pytest.raises(StorageError, match="尚未初始化"):
        IndexMaintenanceService(database, tmp_path / "chroma").preview()
    assert not (tmp_path / "chroma").exists()


def test_repeated_maintenance_releases_its_client_references(indexed):
    from chromadb.api.shared_system_client import SharedSystemClient
    service, _, _, _ = indexed
    before = dict(SharedSystemClient._identifier_to_refcount)
    for _ in range(3):
        service.preview()
    service.clean(service.preview().preview_id)
    assert dict(SharedSystemClient._identifier_to_refcount) == before


def test_clean_preserves_active_queries_unknown_objects_and_sqlite(indexed):
    service, client, collections, fingerprint = indexed
    client.create_collection(name="foreign_collection", embedding_function=None)
    with service.database.connect() as connection:
        before = {table: list(map(tuple, connection.execute(f"SELECT * FROM {table}")))
                  for table in ("collections", "sources", "chunks", "chunks_fts", "active_embedding_profile")}
    inventory = service.preview()
    result = service.clean(inventory.preview_id)
    assert len(result.deleted) == 4 and not result.remaining and not result.error
    assert {item.name for item in client.list_collections()} == {
        "foreign_collection", *(ChromaVectorStore.collection_name(c.id, fingerprint) for c in collections)
    }
    for collection in collections:
        current = client.get_collection(ChromaVectorStore.collection_name(collection.id, fingerprint), embedding_function=None)
        assert current.query(query_embeddings=[[0.1, 0.2]], n_results=1)["ids"] == [["one"]]
    with service.database.connect() as connection:
        for table, rows in before.items():
            assert list(map(tuple, connection.execute(f"SELECT * FROM {table}"))) == rows
    assert service.clean(service.preview().preview_id).deleted == ()
    with pytest.raises(ConflictError):
        service.clean(inventory.preview_id)
    assert SQLiteOperationLogRepository(service.database).list_recent()[0].action == "index_cleanup_finished"


@pytest.mark.parametrize("change", ["profile", "metadata", "replacement", "count", "collection"])
def test_stale_preview_cannot_delete_changed_targets(indexed, change):
    service, client, collections, _ = indexed
    preview = service.preview()
    target = preview.candidates[0]
    if change == "profile":
        settings = EmbeddingSettings(local_model="another")
        service.profiles.activate(settings, embedding_profile_fingerprint(settings))
    elif change == "metadata":
        client.get_collection(target.name).modify(metadata={"ragdb_collection_id": str(uuid4())})
    elif change == "replacement":
        client.delete_collection(target.name)
        client.create_collection(name=target.name, metadata={"ragdb_collection_id": str(target.collection_id)}, embedding_function=None)
    elif change == "count":
        client.get_collection(target.name).add(ids=["two"], embeddings=[[0.2, 0.3]])
    else:
        SQLiteCollectionRepository(service.database).create(Collection(name="new collection"))
    names = {item.name for item in client.list_collections()}
    with pytest.raises(ConflictError, match="预览"):
        service.clean(preview.preview_id)
    assert names == {item.name for item in client.list_collections()}


@pytest.mark.parametrize("operation", ["ingestion", "rebuild"])
def test_clean_respects_other_instance_gate(indexed, operation):
    service, client, _, _ = indexed
    inventory = service.preview()
    gate = SQLiteEmbeddingOperationGate(SQLiteDatabase(service.database.path))
    with getattr(gate, operation)():
        with pytest.raises(StorageError):
            service.clean(inventory.preview_id)
    assert len(client.list_collections()) == 6


def test_partial_failure_stops_then_can_retry_after_restart(indexed, monkeypatch):
    service, client, _, _ = indexed
    original = service.catalog.delete_checked
    calls = []
    def fail_second(*args):
        calls.append(args[0])
        if len(calls) == 2:
            raise RuntimeError("private-server-response")
        original(*args)
    monkeypatch.setattr(service.catalog, "delete_checked", fail_second)
    result = service.clean(service.preview().preview_id)
    assert len(result.deleted) == 1 and len(result.remaining) == 3
    assert len(calls) == 2 and "private" not in result.error
    restarted = IndexMaintenanceService(SQLiteDatabase(service.database.path), service.chroma_directory)
    result = restarted.clean(restarted.preview().preview_id)
    assert len(result.deleted) == 3 and not result.error
    assert len(client.list_collections()) == 2


def test_delete_revalidates_identity_at_execution(indexed, monkeypatch):
    service, client, _, _ = indexed
    target = service.preview().candidates[0]
    original = service.catalog.delete_checked
    def replace_before_delete(*args):
        client.delete_collection(target.name)
        client.create_collection(name=target.name, metadata={"ragdb_collection_id": str(target.collection_id)}, embedding_function=None)
        original(*args)
    monkeypatch.setattr(service.catalog, "delete_checked", replace_before_delete)
    result = service.clean(service.preview().preview_id)
    assert not result.deleted and len(result.remaining) == 4
    assert len(client.list_collections()) == 6


def test_audit_failure_does_not_hide_partial_state(indexed, monkeypatch):
    service, client, _, _ = indexed
    original = SQLiteOperationLogRepository.record
    def fail_finish(self, operation):
        if operation.action == "index_cleanup_finished":
            raise RuntimeError("disk error")
        return original(self, operation)
    monkeypatch.setattr(SQLiteOperationLogRepository, "record", fail_finish)
    result = service.clean(service.preview().preview_id)
    assert len(result.deleted) == 4 and result.audit_warning
    assert not result.remaining and len(client.list_collections()) == 2


def test_failed_start_audit_prevents_all_deletes(indexed, monkeypatch):
    service, client, _, _ = indexed
    def fail(*args):
        raise RuntimeError("disk unavailable")
    monkeypatch.setattr(SQLiteOperationLogRepository, "record", fail)
    with pytest.raises(StorageError, match="未删除"):
        service.clean(service.preview().preview_id)
    assert len(client.list_collections()) == 6
    with SQLiteEmbeddingOperationGate(service.database).ingestion():
        pass


def test_unhealthy_active_index_prevents_cleanup(indexed, monkeypatch):
    service, client, _, _ = indexed
    def fail(*args):
        raise StorageError("活动索引暂时无法检索")
    monkeypatch.setattr(service.catalog, "verify_queryable", fail)
    with pytest.raises(StorageError, match="无法检索"):
        service.clean(service.preview().preview_id)
    assert len(client.list_collections()) == 6


def test_cleanup_recovers_gate_left_by_exited_process(indexed):
    import subprocess
    import sys
    service, client, _, _ = indexed
    code = "\n".join([
        "import os, sys",
        "from pathlib import Path",
        "from ragdb.infrastructure.database import SQLiteDatabase, SQLiteEmbeddingOperationGate",
        "with SQLiteEmbeddingOperationGate(SQLiteDatabase(Path(sys.argv[1]))).rebuild():",
        "    os._exit(17)",
    ])
    child = subprocess.run([sys.executable, "-c", code, str(service.database.path)], capture_output=True, timeout=20)
    assert child.returncode == 17
    with service.database.connect() as connection:
        assert connection.execute("SELECT rebuild_active FROM embedding_operation_gate").fetchone()[0] == 1
    assert len(service.clean(service.preview().preview_id).deleted) == 4
    assert len(client.list_collections()) == 2


def test_cleanup_excludes_ingestion_and_rebuild_while_deleting(indexed, monkeypatch):
    service, _, _, _ = indexed
    original = service.catalog.delete_checked
    def check_gate(*args):
        gate = SQLiteEmbeddingOperationGate(SQLiteDatabase(service.database.path))
        for operation in (gate.ingestion, gate.rebuild):
            with pytest.raises(StorageError):
                with operation():
                    pytest.fail("mutator entered during cleanup")
        original(*args)
    monkeypatch.setattr(service.catalog, "delete_checked", check_gate)
    assert len(service.clean(service.preview().preview_id).deleted) == 4


@pytest.mark.parametrize("active_damage", [None, "missing", "empty"])
def test_rebuild_then_cleanup_retains_search_and_fts(tmp_path, monkeypatch, active_damage):
    from ragdb.application.embedding_rebuild import EmbeddingRebuildService
    from ragdb.domain.models import Source, Chunk
    from ragdb.domain.enums import SourceType, SourceStatus
    from ragdb.infrastructure.database import SQLiteSourceRepository, SQLiteChunkRepository, SQLiteKeywordIndex
    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="合成资料"))
    source = Source(collection_id=collection.id, source_type=SourceType.MANUAL_TEXT,
                    title="合成笔记", uri="manual://test", content_hash="a" * 64,
                    status=SourceStatus.READY, embedding_provider="local",
                    embedding_model="BAAI/bge-small-zh-v1.5", current_generation=1)
    SQLiteSourceRepository(database).create(source)
    chunk = Chunk(id="synthetic", collection_id=collection.id, source_id=source.id,
                  source_content_hash="a" * 64, generation=1, ordinal=0,
                  text="synthetic knowledge", normalized_text="synthetic knowledge")
    SQLiteChunkRepository(database).add_many([chunk])
    fts = SQLiteKeywordIndex(database)
    fts.index([chunk])
    SQLiteEmbeddingProfileRepository(database).initialize(EmbeddingSettings())
    ChromaVectorStore(tmp_path / "chroma").upsert([chunk], [[0.1, 0.2]])
    class Model:
        def embed_texts(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: Model())
    EmbeddingRebuildService(database, tmp_path / "chroma").rebuild(EmbeddingSettings(provider="ollama"))
    service = IndexMaintenanceService(database, tmp_path / "chroma")
    before_fts = fts.search(collection.id, "synthetic", 5)
    if active_damage:
        store = ChromaVectorStore(tmp_path / "chroma", service.profiles.get()[2])
        if active_damage == "missing":
            store.delete_collection(collection.id)
        else:
            store._get_collection(collection.id).delete(ids=[chunk.id])
        with pytest.raises(StorageError, match="缺少活动"):
            service.clean(service.preview().preview_id)
        assert ChromaVectorStore(tmp_path / "chroma").has_chunks(collection.id, [chunk.id])
        return
    result = service.clean(service.preview().preview_id)
    assert len(result.deleted) == 1 and not result.error
    active = service.profiles.get()
    restarted = ChromaVectorStore(tmp_path / "chroma", active[2])
    assert restarted.search(collection.id, [0.1, 0.2, 0.3], 5)[0].chunk.id == chunk.id
    assert fts.search(collection.id, "synthetic", 5) == before_fts
    assert before_fts
