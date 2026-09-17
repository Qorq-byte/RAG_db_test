from pathlib import Path

import pytest

from ragdb.domain.enums import RetrievalRoute, SourceType
from ragdb.domain.models import Chunk, Collection, Source
from ragdb.infrastructure.database.fts import (
    SQLiteKeywordIndex,
    build_match_query,
    normalize_for_fts,
)
from ragdb.infrastructure.database.repository import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteDatabase,
    SQLiteSourceRepository,
)


CONTENT_HASH = "c" * 64


@pytest.fixture
def indexed_data(tmp_path: Path) -> tuple[SQLiteKeywordIndex, Collection, Source, list[Chunk]]:
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    collection = Collection(name="人工智能")
    SQLiteCollectionRepository(database).create(collection)
    source = Source(
        collection_id=collection.id,
        source_type=SourceType.MARKDOWN,
        title="Transformer 课程笔记",
        uri="notes.md",
        content_hash=CONTENT_HASH,
    )
    SQLiteSourceRepository(database).create(source)
    chunks = [
        Chunk(
            id="attention",
            collection_id=collection.id,
            source_id=source.id,
            source_content_hash=CONTENT_HASH,
            generation=1,
            ordinal=0,
            text="自注意力机制能够建模长距离依赖。",
            normalized_text="自注意力机制能够建模长距离依赖。",
        ),
        Chunk(
            id="cnn",
            collection_id=collection.id,
            source_id=source.id,
            source_content_hash=CONTENT_HASH,
            generation=1,
            ordinal=1,
            text="Convolutional networks use local receptive fields.",
            normalized_text="convolutional networks use local receptive fields.",
        ),
    ]
    SQLiteChunkRepository(database).add_many(chunks)
    index = SQLiteKeywordIndex(database)
    index.index(chunks)
    return index, collection, source, chunks


def test_chinese_and_english_normalization() -> None:
    assert normalize_for_fts("Transformer 注意力") == "transformer 注 意 力"
    assert build_match_query("Transformer 注意力") == '"transformer" AND "注 意 力"'


def test_keyword_search_finds_chinese_phrase(indexed_data: tuple) -> None:
    index, collection, _, _ = indexed_data

    results = index.search(collection.id, "注意力机制", limit=5)

    assert [result.chunk.id for result in results] == ["attention"]
    assert results[0].route == RetrievalRoute.KEYWORD


def test_keyword_search_finds_english_term(indexed_data: tuple) -> None:
    index, collection, _, _ = indexed_data

    results = index.search(collection.id, "convolutional networks", limit=5)

    assert [result.chunk.id for result in results] == ["cnn"]


def test_reindexing_chunk_does_not_duplicate_results(indexed_data: tuple) -> None:
    index, collection, _, chunks = indexed_data
    index.index(chunks)

    results = index.search(collection.id, "注意力", limit=5)

    assert [result.chunk.id for result in results] == ["attention"]


def test_delete_source_generation_removes_fts_rows(indexed_data: tuple) -> None:
    index, collection, source, _ = indexed_data

    deleted = index.delete_source_generation(collection.id, source.id, 1)

    assert deleted == 2
    assert index.search(collection.id, "注意力", limit=5) == []


def test_deleting_source_cascades_to_fts_rows(indexed_data: tuple) -> None:
    index, _, source, _ = indexed_data

    SQLiteSourceRepository(index.database).delete(source.id)

    with index.database.connect() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE source_id = ?",
            (str(source.id),),
        ).fetchone()[0]
    assert remaining == 0
