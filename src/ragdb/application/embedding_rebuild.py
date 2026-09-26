"""Build and atomically publish a new embedding index across all sources."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from ragdb.config import EmbeddingSettings
from ragdb.domain.errors import StorageError
from ragdb.domain.models import Source
from ragdb.infrastructure.database import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteEmbeddingOperationGate,
    SQLiteEmbeddingProfileRepository,
    SQLiteSourceRepository,
)
from ragdb.infrastructure.database.repository import SQLiteDatabase, embedding_profile_fingerprint
from ragdb.infrastructure.embeddings import create_embedding_provider
from ragdb.infrastructure.vectorstore import ChromaVectorStore


@dataclass(frozen=True, slots=True)
class EmbeddingRebuildProgress:
    completed_chunks: int
    total_chunks: int
    collection_id: UUID | None = None
    source_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingRebuildResult:
    fingerprint: str
    chunk_count: int
    collection_count: int
    changed: bool
    configuration_warning: str | None = None


class EmbeddingRebuildCancelled(RuntimeError):
    """Raised when the caller cancels before the active profile is published."""


class EmbeddingRebuildService:
    def __init__(
        self,
        database: SQLiteDatabase,
        chroma_directory: Path,
        *,
        batch_size: int = 32,
        gate: SQLiteEmbeddingOperationGate | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.database = database
        self.chroma_directory = chroma_directory
        self.batch_size = batch_size
        self.gate = gate or SQLiteEmbeddingOperationGate(database)
        self.collections = SQLiteCollectionRepository(database)
        self.sources = SQLiteSourceRepository(database)
        self.chunks = SQLiteChunkRepository(database)
        self.profiles = SQLiteEmbeddingProfileRepository(database)

    def rebuild(
        self,
        settings: EmbeddingSettings,
        *,
        on_progress: Callable[[EmbeddingRebuildProgress], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> EmbeddingRebuildResult:
        fingerprint = embedding_profile_fingerprint(settings)
        self._check_cancel(should_cancel)
        with self.gate.rebuild():
            active = self.profiles.get()
            if active is None:
                raise StorageError("请先初始化当前活动嵌入配置，再执行重建。")
            _, active_fingerprint, active_namespace = active
            if fingerprint == active_fingerprint and active_namespace == fingerprint:
                return EmbeddingRebuildResult(fingerprint, 0, 0, False)
            self._check_cancel(should_cancel)
            provider = create_embedding_provider(settings)
            probe = provider.embed_texts(["RAG embedding profile verification."])
            self._validate_vectors(probe, 1)
            self._check_cancel(should_cancel)

            collections = list(self.collections.list_all())
            work: list[Source] = []
            for collection in collections:
                for source in self.sources.list_for_collection(collection.id):
                    if source.current_generation < 1:
                        continue
                    work.append(source)
            with self.database.connect() as connection:
                total = connection.execute(
                    "SELECT COUNT(*) FROM chunks c JOIN sources s ON c.source_id = s.id "
                    "AND c.generation = s.current_generation"
                ).fetchone()[0]
            target = ChromaVectorStore(self.chroma_directory, namespace_id=fingerprint)
            completed = 0
            try:
                # This namespace is not active. It may contain a stale interrupted build.
                for collection in collections:
                    target.delete_collection(collection.id)
                if on_progress:
                    on_progress(EmbeddingRebuildProgress(0, total))
                for source in work:
                    collection_id, source_id = source.collection_id, source.id
                    source_chunks = self.chunks.list_for_source(source_id, source.current_generation)
                    if not source_chunks:
                        raise StorageError("资料的当前代次缺少切片，活动索引未切换。")
                    for start in range(0, len(source_chunks), self.batch_size):
                        self._check_cancel(should_cancel)
                        batch = source_chunks[start : start + self.batch_size]
                        vectors = provider.embed_texts([chunk.text for chunk in batch])
                        self._validate_vectors(vectors, len(batch))
                        if len(vectors[0]) != len(probe[0]):
                            raise StorageError("嵌入模型在重建期间改变了向量维度。")
                        self._check_cancel(should_cancel)
                        target.upsert(batch, vectors)
                        if not target.has_chunks(collection_id, [chunk.id for chunk in batch]):
                            raise StorageError("暂存向量校验失败，活动索引未切换。")
                        completed += len(batch)
                        if on_progress:
                            on_progress(EmbeddingRebuildProgress(completed, total, collection_id, source_id))
                self._check_cancel(should_cancel)
                self.profiles.activate(settings, fingerprint)
                return EmbeddingRebuildResult(fingerprint, completed, len(collections), True)
            except BaseException as exc:
                for collection in collections:
                    try:
                        target.delete_collection(collection.id)
                    except Exception:
                        exc.add_note("部分暂存向量清理失败；旧索引仍然活动，重试时会重新清理暂存空间。")
                raise
            finally:
                target.close()

    @staticmethod
    def _check_cancel(should_cancel: Callable[[], bool] | None) -> None:
        if should_cancel is not None and should_cancel():
            raise EmbeddingRebuildCancelled("嵌入重建已取消；旧索引仍保持活动状态。")

    @staticmethod
    def _validate_vectors(vectors: Sequence[Sequence[float]], expected_count: int) -> None:
        if len(vectors) != expected_count or any(not vector for vector in vectors):
            raise StorageError("嵌入模型返回的向量数量或内容无效。")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for vector in vectors for value in vector
        ):
            raise StorageError("嵌入模型返回了维度不一致或非有限数值向量。")
