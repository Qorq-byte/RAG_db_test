from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import pytest

from ragdb.application.ingestion import LocalIngestionService
from ragdb.config import ChunkingSettings
from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Chunk, Collection, RetrievedChunk
from ragdb.infrastructure.chunking import StructuredChunker
from ragdb.infrastructure.database import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteDatabase,
    SQLiteKeywordIndex,
    SQLiteSourceRepository,
    SQLiteTaskRepository,
)
from ragdb.infrastructure.parsers import ParserRegistry


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-v1"
    dimension = 2

    def __init__(self) -> None:
        self.fail = False

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if self.fail:
            raise RuntimeError("embedding service unavailable")
        return [[float(len(text)), 1.0] for text in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.records: dict[str, Chunk] = {}

    def upsert(self, chunks, embeddings) -> None:
        self.records.update({chunk.id: chunk for chunk in chunks})

    def search(self, collection_id, query_embedding, limit, filters=None) -> Sequence[RetrievedChunk]:
        return []

    def delete_source_generation(self, collection_id: UUID, source_id: UUID, generation: int) -> int:
        ids = [key for key, chunk in self.records.items() if chunk.source_id == source_id and chunk.generation == generation]
        for key in ids:
            del self.records[key]
        return len(ids)

    def delete_collection(self, collection_id: UUID) -> None:
        self.records = {key: chunk for key, chunk in self.records.items() if chunk.collection_id != collection_id}


def test_failed_reindex_keeps_previous_sqlite_and_vector_generation(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="资料"))
    sources = SQLiteSourceRepository(database)
    chunks = SQLiteChunkRepository(database)
    provider = FakeEmbeddingProvider()
    vectors = FakeVectorStore()
    service = LocalIngestionService(
        sources, chunks, SQLiteTaskRepository(database), ParserRegistry(),
        StructuredChunker(ChunkingSettings(max_characters=200, overlap_characters=20)),
        SQLiteKeywordIndex(database), provider, vectors,
    )
    path = tmp_path / "notes.txt"
    path.write_text("stable indexed knowledge", encoding="utf-8")
    first = service.ingest_file(collection, path)
    assert first.source is not None

    path.write_text("replacement knowledge", encoding="utf-8")
    provider.fail = True
    with pytest.raises(DocumentParseError, match="embedding service"):
        service.ingest_file(collection, path)

    stored = sources.get(first.source.id)
    assert stored is not None
    assert stored.current_generation == 1
    assert stored.status.value == "ready"
    assert {chunk.generation for chunk in chunks.list_for_source(first.source.id)} == {1}
    assert {chunk.generation for chunk in vectors.records.values()} == {1}

    provider.fail = False
    updated = service.ingest_file(collection, path)
    assert updated.source is not None
    assert updated.source.current_generation == 2
    assert {chunk.generation for chunk in chunks.list_for_source(first.source.id)} == {2}
    assert {chunk.generation for chunk in vectors.records.values()} == {2}
