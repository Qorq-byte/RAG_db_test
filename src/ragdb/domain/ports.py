"""Protocol interfaces between application services and infrastructure."""

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import JsonValue

from ragdb.domain.models import (
    Chunk,
    Collection,
    Document,
    IngestionTask,
    RetrievedChunk,
    Source,
)


@runtime_checkable
class CollectionRepository(Protocol):
    def create(self, collection: Collection) -> Collection: ...

    def get(self, collection_id: UUID) -> Collection | None: ...

    def get_by_name(self, name: str) -> Collection | None: ...

    def list_all(self) -> Sequence[Collection]: ...

    def delete(self, collection_id: UUID) -> bool: ...


@runtime_checkable
class SourceRepository(Protocol):
    def create(self, source: Source) -> Source: ...

    def get(self, source_id: UUID) -> Source | None: ...

    def get_by_uri(self, collection_id: UUID, uri: str) -> Source | None: ...

    def list_for_collection(self, collection_id: UUID) -> Sequence[Source]: ...

    def update(self, source: Source) -> Source: ...

    def delete(self, source_id: UUID) -> bool: ...


@runtime_checkable
class TaskRepository(Protocol):
    def create(self, task: IngestionTask) -> IngestionTask: ...

    def get(self, task_id: UUID) -> IngestionTask | None: ...

    def list_for_collection(self, collection_id: UUID, limit: int = 20) -> Sequence[IngestionTask]: ...

    def update(self, task: IngestionTask) -> IngestionTask: ...


@runtime_checkable
class ChunkRepository(Protocol):
    def add_many(self, chunks: Sequence[Chunk]) -> None: ...

    def list_for_source(
        self,
        source_id: UUID,
        generation: int | None = None,
    ) -> Sequence[Chunk]: ...

    def delete_source_generation(self, source_id: UUID, generation: int) -> int: ...

    def delete_for_source(self, source_id: UUID) -> int: ...


@runtime_checkable
class DocumentParser(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def supports(self, source: Source) -> bool: ...

    def parse(self, source: Source) -> Document: ...


@runtime_checkable
class Chunker(Protocol):
    def chunk(
        self,
        document: Document,
        collection_id: UUID,
        source_content_hash: str,
        generation: int,
    ) -> Sequence[Chunk]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


@runtime_checkable
class VectorStore(Protocol):
    def upsert(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None: ...

    def search(
        self,
        collection_id: UUID,
        query_embedding: Sequence[float],
        limit: int,
        filters: Mapping[str, JsonValue] | None = None,
    ) -> Sequence[RetrievedChunk]: ...

    def delete_source_generation(
        self,
        collection_id: UUID,
        source_id: UUID,
        generation: int,
    ) -> int: ...

    def delete_collection(self, collection_id: UUID) -> None: ...


@runtime_checkable
class KeywordIndex(Protocol):
    def index(self, chunks: Sequence[Chunk]) -> None: ...

    def search(
        self,
        collection_id: UUID,
        query: str,
        limit: int,
        filters: Mapping[str, JsonValue] | None = None,
    ) -> Sequence[RetrievedChunk]: ...

    def delete_source_generation(
        self,
        collection_id: UUID,
        source_id: UUID,
        generation: int,
    ) -> int: ...


@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        limit: int,
    ) -> Sequence[RetrievedChunk]: ...
