from datetime import timedelta
from pathlib import Path

import pytest

from ragdb.domain.enums import SourceStatus, SourceType, TaskStatus
from ragdb.domain.errors import CollectionAlreadyExistsError, StorageError
from ragdb.domain.models import (
    Chunk,
    Collection,
    IngestionTask,
    Source,
    SourcePosition,
    utc_now,
)
from ragdb.infrastructure.database.repository import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteDatabase,
    SQLiteSourceRepository,
    SQLiteTaskRepository,
)
from ragdb.infrastructure.database.schema import SCHEMA_VERSION


CONTENT_HASH = "b" * 64


@pytest.fixture
def database(tmp_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    return database


def test_schema_initialization_is_idempotent(database: SQLiteDatabase) -> None:
    database.initialize()

    with database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }

    assert version == SCHEMA_VERSION
    assert {"collections", "sources", "chunks", "chunks_fts"} <= tables


def test_collection_repository_crud(database: SQLiteDatabase) -> None:
    repository = SQLiteCollectionRepository(database)
    collection = Collection(name="深度学习", description="课程资料")

    repository.create(collection)

    assert repository.get(collection.id) == collection
    assert repository.get_by_name("深度学习") == collection
    assert repository.list_all() == [collection]
    assert repository.delete(collection.id) is True
    assert repository.get(collection.id) is None
    assert repository.delete(collection.id) is False


def test_collection_name_is_unique_case_insensitively(
    database: SQLiteDatabase,
) -> None:
    repository = SQLiteCollectionRepository(database)
    repository.create(Collection(name="Transformers"))

    with pytest.raises(CollectionAlreadyExistsError):
        repository.create(Collection(name="transformers"))


def test_source_and_chunk_round_trip(database: SQLiteDatabase) -> None:
    collection = Collection(name="论文")
    SQLiteCollectionRepository(database).create(collection)
    source_repository = SQLiteSourceRepository(database)
    chunk_repository = SQLiteChunkRepository(database)
    source = Source(
        collection_id=collection.id,
        source_type=SourceType.PDF,
        title="Attention Is All You Need",
        uri="D:/papers/attention.pdf",
        content_hash=CONTENT_HASH,
        status=SourceStatus.PROCESSING,
        metadata={"author": "Vaswani et al."},
    )
    source_repository.create(source)
    chunks = [
        Chunk(
            id=f"chunk-{ordinal}",
            collection_id=collection.id,
            source_id=source.id,
            source_content_hash=CONTENT_HASH,
            generation=1,
            ordinal=ordinal,
            text=f"chunk text {ordinal}",
            normalized_text=f"chunk text {ordinal}",
            position=SourcePosition(page=ordinal + 1),
            metadata={"kind": "paragraph"},
        )
        for ordinal in range(2)
    ]
    chunk_repository.add_many(chunks)

    loaded_source = source_repository.get_by_uri(collection.id, source.uri)
    loaded_chunks = chunk_repository.list_for_source(source.id, generation=1)

    assert loaded_source == source
    assert list(loaded_chunks) == chunks

    updated_source = source.model_copy(
        update={
            "status": SourceStatus.READY,
            "current_generation": 1,
            "updated_at": source.updated_at + timedelta(seconds=1),
        }
    )
    source_repository.update(updated_source)
    assert source_repository.get(source.id) == updated_source
    assert chunk_repository.delete_source_generation(source.id, 1) == 2
    assert chunk_repository.list_for_source(source.id) == []


def test_source_with_unknown_collection_is_storage_error(
    database: SQLiteDatabase,
) -> None:
    source = Source(
        collection_id=Collection(name="不存在").id,
        source_type=SourceType.TEXT,
        title="孤立资料",
        uri="text://orphan",
        content_hash=CONTENT_HASH,
    )

    with pytest.raises(StorageError, match="保存资料失败"):
        SQLiteSourceRepository(database).create(source)


def test_deleting_collection_cascades_to_sources_and_chunks(
    database: SQLiteDatabase,
) -> None:
    collection = Collection(name="待删除")
    collection_repository = SQLiteCollectionRepository(database)
    source_repository = SQLiteSourceRepository(database)
    chunk_repository = SQLiteChunkRepository(database)
    collection_repository.create(collection)
    source = Source(
        collection_id=collection.id,
        source_type=SourceType.TEXT,
        title="文本",
        uri="text://one",
        content_hash=CONTENT_HASH,
    )
    source_repository.create(source)
    chunk_repository.add_many(
        [
            Chunk(
                id="cascade-chunk",
                collection_id=collection.id,
                source_id=source.id,
                source_content_hash=CONTENT_HASH,
                generation=1,
                ordinal=0,
                text="content",
                normalized_text="content",
            )
        ]
    )

    collection_repository.delete(collection.id)

    assert source_repository.get(source.id) is None
    assert chunk_repository.list_for_source(source.id) == []


def test_task_repository_round_trip(database: SQLiteDatabase) -> None:
    collection = Collection(name="任务")
    SQLiteCollectionRepository(database).create(collection)
    repository = SQLiteTaskRepository(database)
    task = IngestionTask(collection_id=collection.id, status=TaskStatus.RUNNING)
    repository.create(task)

    finished = task.model_copy(
        update={
            "status": TaskStatus.COMPLETED,
            "finished_at": utc_now(),
            "succeeded": 2,
        }
    )
    repository.update(finished)

    assert repository.get(task.id) == finished
