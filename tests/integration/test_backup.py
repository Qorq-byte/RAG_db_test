import json
import sqlite3
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from typer.testing import CliRunner

from ragdb.application.backup import BackupService
from ragdb.cli import app
from ragdb.config import AppSettings, StorageSettings
from ragdb.domain.errors import ConflictError, StorageError
from ragdb.domain.models import Collection
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteCollectionRepository, SQLiteEmbeddingOperationGate
from ragdb.infrastructure.vectorstore.clients import open_client, close_client


@pytest.fixture
def library(tmp_path):
    settings = AppSettings(storage=StorageSettings(data_dir=tmp_path / "library"))
    service = BackupService(settings)
    service.database.initialize()
    SQLiteCollectionRepository(service.database).create(Collection(name="中文资料"))
    client = open_client(service.chroma)
    try:
        collection = client.create_collection("backup_test", embedding_function=None)
        collection.add(ids=["a", "b"], embeddings=[[1., 0.], [0., 1.]],
                       documents=["正文一", "正文二"], metadatas=[{"generation": 1}, {"generation": 2}])
    finally:
        close_client(client)
    return service


def test_backup_restore_preserves_sqlite_vectors_settings_and_original(library, tmp_path):
    from pydantic import SecretStr
    library.settings.chat.cloud_api_key = SecretStr("DO-NOT-BACK-UP-THIS-KEY")
    archive = tmp_path / "backup.zip"
    result = library.create(archive)
    assert result["collections"] == 1
    assert BackupService.verify(archive)["valid"]
    config = BackupService.restore(archive, tmp_path / "restored")
    assert config.is_file()
    assert "cloud_api_key" not in config.read_text(encoding="utf-8")
    with ZipFile(archive) as package:
        assert b"DO-NOT-BACK-UP" not in package.read("settings.json")
    restored = SQLiteDatabase(config.parent / "ragdb.sqlite3")
    assert SQLiteCollectionRepository(restored).list_all()[0].name == "中文资料"
    with restored.connect() as connection:
        assert connection.execute("SELECT rebuild_active FROM embedding_operation_gate").fetchone()[0] == 0
    client = open_client(config.parent / "chroma")
    try:
        collection = client.get_collection("backup_test", embedding_function=None)
        assert collection.get(include=["documents"])["documents"] == ["正文一", "正文二"]
        assert collection.query(query_embeddings=[[1., 0.]], n_results=1)["ids"] == [["a"]]
    finally:
        close_client(client)
    assert SQLiteCollectionRepository(library.database).list_all()[0].name == "中文资料"


def test_backup_preserves_all_application_tables(tmp_path):
    from ragdb.domain.models import Source, Chunk, Conversation, LearningArtifact
    from ragdb.domain.enums import SourceType, SourceStatus, ArtifactType
    from ragdb.infrastructure.database import (SQLiteSourceRepository, SQLiteChunkRepository,
        SQLiteKeywordIndex, SQLiteConversationRepository, SQLiteArtifactRepository,
        SQLiteEmbeddingProfileRepository)
    from ragdb.infrastructure.vectorstore import ChromaVectorStore

    settings = AppSettings(storage=StorageSettings(data_dir=tmp_path / "full"))
    service = BackupService(settings)
    service.database.initialize()
    collection = SQLiteCollectionRepository(service.database).create(Collection(name="完整库"))
    source = Source(collection_id=collection.id, source_type=SourceType.MANUAL_TEXT,
        title="资料", uri="manual://backup", content_hash="a" * 64, status=SourceStatus.READY,
        current_generation=1, embedding_provider="local", embedding_model=settings.embedding.local_model)
    SQLiteSourceRepository(service.database).create(source)
    chunk = Chunk(id="full-chunk", collection_id=collection.id, source_id=source.id,
        source_content_hash="a" * 64, generation=1, ordinal=0, text="backup evidence", normalized_text="backup evidence")
    SQLiteChunkRepository(service.database).add_many([chunk])
    SQLiteKeywordIndex(service.database).index([chunk])
    SQLiteEmbeddingProfileRepository(service.database).initialize(settings.embedding)
    SQLiteConversationRepository(service.database).create(Conversation(collection_id=collection.id,
        title="对话", provider="local", model="test"))
    SQLiteArtifactRepository(service.database).create(LearningArtifact(collection_id=collection.id,
        artifact_type=ArtifactType.SUMMARY, title="摘要", content="学习内容", provider="local", model="test"), [])
    with ChromaVectorStore(service.chroma) as vectors:
        vectors.upsert([chunk], [[1., 0.]])
    archive = tmp_path / "full.zip"
    service.create(archive)
    restored = BackupService.restore(archive, tmp_path / "roundtrip")
    database = SQLiteDatabase(restored.parent / "ragdb.sqlite3")
    with service.database.connect() as before, database.connect() as after:
        for name in ["collections", "sources", "chunks", "chunks_fts", "conversations", "learning_artifacts", "active_embedding_profile"]:
            assert list(map(tuple, before.execute(f'SELECT * FROM "{name}"'))) == list(map(tuple, after.execute(f'SELECT * FROM "{name}"')))
    assert SQLiteKeywordIndex(database).search(collection.id, "evidence", 5)
    with ChromaVectorStore(restored.parent / "chroma") as vectors:
        assert vectors.search(collection.id, [1., 0.], 1)[0].chunk.id == chunk.id


def test_mutation_lease_blocks_backup(library, tmp_path):
    with SQLiteEmbeddingOperationGate(library.database).ingestion():
        with pytest.raises(StorageError):
            library.create(tmp_path / "blocked.zip")
    assert not (tmp_path / "blocked.zip").exists()


def test_refuse_existing_archive_and_restore_directory(library, tmp_path):
    archive = tmp_path / "backup.zip"
    library.create(archive)
    with pytest.raises(ConflictError):
        library.create(archive)
    with pytest.raises(ConflictError):
        BackupService.restore(archive, library.settings.storage.data_dir)


@pytest.mark.parametrize("fault", ["checksum", "traversal", "duplicate"])
def test_invalid_archive_never_publishes_destination(library, tmp_path, fault):
    original = tmp_path / "original.zip"
    library.create(original)
    bad = tmp_path / "bad.zip"
    with ZipFile(original) as source, ZipFile(bad, "w", ZIP_DEFLATED) as target:
        manifest = json.loads(source.read("manifest.json"))
        for name in source.namelist():
            if name == "manifest.json":
                continue
            if fault == "checksum" and name == "settings.json":
                target.writestr(name, b"damaged")
            else:
                target.writestr(name, source.read(name))
        if fault == "traversal":
            manifest["files"]["../escape"] = "a" * 64
            target.writestr("../escape", b"unsafe")
        target.writestr("manifest.json", json.dumps(manifest))
        if fault == "duplicate":
            target.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(StorageError):
        BackupService.restore(bad, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    assert not (tmp_path / "escape").exists()


def test_cli_verify_restore_without_current_library(library, tmp_path):
    archive = tmp_path / "backup.zip"
    library.create(archive)
    runner = CliRunner()
    result = runner.invoke(app, ["backup", "verify", str(archive)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["backup", "restore", str(archive), str(tmp_path / "cli-restored")])
    assert result.exit_code == 0, result.output
