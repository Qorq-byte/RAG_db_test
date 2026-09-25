from uuid import uuid4

import pytest

from ragdb.application.index_maintenance import IndexMaintenanceService
from ragdb.config import EmbeddingSettings
from ragdb.domain.errors import StorageError
from ragdb.domain.models import Collection
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteCollectionRepository, SQLiteEmbeddingProfileRepository
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.vectorstore import ChromaVectorStore


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
            )
            stored.add(ids=["one"], embeddings=[[0.1, 0.2]], documents=["synthetic"])
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
