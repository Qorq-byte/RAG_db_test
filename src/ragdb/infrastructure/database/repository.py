"""SQLite repositories for domain objects."""

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

from ragdb.domain.enums import SourceStatus, SourceType, TaskStatus
from ragdb.domain.errors import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    SourceAlreadyExistsError,
    SourceNotFoundError,
    StorageError,
    TaskNotFoundError,
)
from ragdb.domain.models import (
    Chunk,
    Collection,
    IngestionTask,
    Source,
    SourcePosition,
)
from ragdb.infrastructure.database.schema import initialize_schema


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(value: str) -> dict[str, object]:
    loaded = json.loads(value)
    if not isinstance(loaded, dict):
        raise StorageError("数据库中的 JSON 字段不是对象")
    return loaded


def _is_unique_constraint(error: sqlite3.IntegrityError) -> bool:
    return getattr(error, "sqlite_errorname", None) in {
        "SQLITE_CONSTRAINT_PRIMARYKEY",
        "SQLITE_CONSTRAINT_UNIQUE",
    }


class SQLiteDatabase:
    """Open short-lived, transaction-scoped SQLite connections."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            initialize_schema(connection)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _collection_from_row(row: sqlite3.Row) -> Collection:
    return Collection(
        id=UUID(row["id"]),
        name=row["name"],
        description=row["description"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _source_from_row(row: sqlite3.Row) -> Source:
    return Source(
        id=UUID(row["id"]),
        collection_id=UUID(row["collection_id"]),
        source_type=SourceType(row["source_type"]),
        title=row["title"],
        uri=row["uri"],
        content_hash=row["content_hash"],
        status=SourceStatus(row["status"]),
        metadata=_load_json(row["metadata_json"]),
        imported_at=datetime.fromisoformat(row["imported_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        parser_name=row["parser_name"],
        parser_version=row["parser_version"],
        embedding_provider=row["embedding_provider"],
        embedding_model=row["embedding_model"],
        current_generation=row["current_generation"],
        error_message=row["error_message"],
    )


def _chunk_from_row(row: sqlite3.Row) -> Chunk:
    return Chunk(
        id=row["id"],
        collection_id=UUID(row["collection_id"]),
        source_id=UUID(row["source_id"]),
        source_content_hash=row["source_content_hash"],
        generation=row["generation"],
        ordinal=row["ordinal"],
        text=row["text"],
        normalized_text=row["normalized_text"],
        position=SourcePosition.model_validate(_load_json(row["position_json"])),
        metadata=_load_json(row["metadata_json"]),
    )


def _task_from_row(row: sqlite3.Row) -> IngestionTask:
    return IngestionTask(
        id=UUID(row["id"]),
        collection_id=UUID(row["collection_id"]),
        status=TaskStatus(row["status"]),
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=(
            datetime.fromisoformat(row["finished_at"])
            if row["finished_at"] is not None
            else None
        ),
        succeeded=row["succeeded"],
        updated=row["updated"],
        skipped=row["skipped"],
        failed=row["failed"],
    )


class SQLiteCollectionRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, collection: Collection) -> Collection:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO collections (id, name, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(collection.id),
                        collection.name,
                        collection.description,
                        collection.created_at.isoformat(),
                        collection.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise CollectionAlreadyExistsError(collection.name) from exc
        return collection

    def get(self, collection_id: UUID) -> Collection | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM collections WHERE id = ?", (str(collection_id),)
            ).fetchone()
        return _collection_from_row(row) if row is not None else None

    def get_by_name(self, name: str) -> Collection | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM collections WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
        return _collection_from_row(row) if row is not None else None

    def list_all(self) -> Sequence[Collection]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM collections ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [_collection_from_row(row) for row in rows]

    def delete(self, collection_id: UUID) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM collections WHERE id = ?", (str(collection_id),)
            )
        return cursor.rowcount > 0


class SQLiteSourceRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, source: Source) -> Source:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO sources (
                        id, collection_id, source_type, title, uri, content_hash,
                        status, metadata_json, imported_at, updated_at, parser_name,
                        parser_version, embedding_provider, embedding_model,
                        current_generation, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._values(source),
                )
        except sqlite3.IntegrityError as exc:
            if _is_unique_constraint(exc):
                raise SourceAlreadyExistsError(source.uri) from exc
            raise StorageError("保存资料失败") from exc
        return source

    @staticmethod
    def _values(source: Source) -> tuple[object, ...]:
        return (
            str(source.id),
            str(source.collection_id),
            source.source_type.value,
            source.title,
            source.uri,
            source.content_hash,
            source.status.value,
            _dump_json(source.metadata),
            source.imported_at.isoformat(),
            source.updated_at.isoformat(),
            source.parser_name,
            source.parser_version,
            source.embedding_provider,
            source.embedding_model,
            source.current_generation,
            source.error_message,
        )

    def get(self, source_id: UUID) -> Source | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (str(source_id),)
            ).fetchone()
        return _source_from_row(row) if row is not None else None

    def get_by_uri(self, collection_id: UUID, uri: str) -> Source | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE collection_id = ? AND uri = ?",
                (str(collection_id), uri),
            ).fetchone()
        return _source_from_row(row) if row is not None else None

    def list_for_collection(self, collection_id: UUID) -> Sequence[Source]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sources
                WHERE collection_id = ?
                ORDER BY title COLLATE NOCASE, uri
                """,
                (str(collection_id),),
            ).fetchall()
        return [_source_from_row(row) for row in rows]

    def update(self, source: Source) -> Source:
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE sources SET
                        collection_id = ?, source_type = ?, title = ?, uri = ?,
                        content_hash = ?, status = ?, metadata_json = ?, imported_at = ?,
                        updated_at = ?, parser_name = ?, parser_version = ?,
                        embedding_provider = ?, embedding_model = ?,
                        current_generation = ?, error_message = ?
                    WHERE id = ?
                    """,
                    self._values(source)[1:] + (str(source.id),),
                )
        except sqlite3.IntegrityError as exc:
            if _is_unique_constraint(exc):
                raise SourceAlreadyExistsError(source.uri) from exc
            raise StorageError("更新资料失败") from exc
        if cursor.rowcount == 0:
            raise SourceNotFoundError(source.id)
        return source

    def delete(self, source_id: UUID) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sources WHERE id = ?", (str(source_id),)
            )
        return cursor.rowcount > 0


class SQLiteChunkRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add_many(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        values = [
            (
                chunk.id,
                str(chunk.collection_id),
                str(chunk.source_id),
                chunk.source_content_hash,
                chunk.generation,
                chunk.ordinal,
                chunk.text,
                chunk.normalized_text,
                _dump_json(chunk.position.model_dump(mode="json")),
                _dump_json(chunk.metadata),
            )
            for chunk in chunks
        ]
        try:
            with self.database.connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO chunks (
                        id, collection_id, source_id, source_content_hash,
                        generation, ordinal, text, normalized_text,
                        position_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError("保存文本切片失败") from exc

    def list_for_source(
        self,
        source_id: UUID,
        generation: int | None = None,
    ) -> Sequence[Chunk]:
        query = "SELECT * FROM chunks WHERE source_id = ?"
        parameters: list[object] = [str(source_id)]
        if generation is not None:
            query += " AND generation = ?"
            parameters.append(generation)
        query += " ORDER BY generation, ordinal"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_chunk_from_row(row) for row in rows]

    def delete_source_generation(self, source_id: UUID, generation: int) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM chunks WHERE source_id = ? AND generation = ?",
                (str(source_id), generation),
            )
        return cursor.rowcount

    def delete_for_source(self, source_id: UUID) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM chunks WHERE source_id = ?", (str(source_id),)
            )
        return cursor.rowcount


class SQLiteGenerationRepository:
    """Atomically publish a source generation and its SQLite chunks."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def activate(self, source: Source, chunks: Sequence[Chunk]) -> None:
        values = [
            (chunk.id, str(chunk.collection_id), str(chunk.source_id), chunk.source_content_hash,
             chunk.generation, chunk.ordinal, chunk.text, chunk.normalized_text,
             _dump_json(chunk.position.model_dump(mode="json")), _dump_json(chunk.metadata))
            for chunk in chunks
        ]
        with self.database.connect() as connection:
            connection.executemany(
                """INSERT INTO chunks (id, collection_id, source_id, source_content_hash,
                generation, ordinal, text, normalized_text, position_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values,
            )
            cursor = connection.execute(
                """UPDATE sources SET collection_id=?, source_type=?, title=?, uri=?, content_hash=?,
                status=?, metadata_json=?, imported_at=?, updated_at=?, parser_name=?, parser_version=?,
                embedding_provider=?, embedding_model=?, current_generation=?, error_message=? WHERE id=?""",
                SQLiteSourceRepository._values(source)[1:] + (str(source.id),),
            )
            if cursor.rowcount == 0:
                raise SourceNotFoundError(source.id)


class SQLiteTaskRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create(self, task: IngestionTask) -> IngestionTask:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO ingestion_tasks (
                        id, collection_id, status, started_at, finished_at,
                        succeeded, updated, skipped, failed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._values(task),
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError("保存导入任务失败") from exc
        return task

    @staticmethod
    def _values(task: IngestionTask) -> tuple[object, ...]:
        return (
            str(task.id),
            str(task.collection_id),
            task.status.value,
            task.started_at.isoformat(),
            task.finished_at.isoformat() if task.finished_at is not None else None,
            task.succeeded,
            task.updated,
            task.skipped,
            task.failed,
        )

    def get(self, task_id: UUID) -> IngestionTask | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ingestion_tasks WHERE id = ?", (str(task_id),)
            ).fetchone()
        return _task_from_row(row) if row is not None else None

    def update(self, task: IngestionTask) -> IngestionTask:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE ingestion_tasks SET
                    collection_id = ?, status = ?, started_at = ?, finished_at = ?,
                    succeeded = ?, updated = ?, skipped = ?, failed = ?
                WHERE id = ?
                """,
                self._values(task)[1:] + (str(task.id),),
            )
        if cursor.rowcount == 0:
            raise TaskNotFoundError(task.id)
        return task
