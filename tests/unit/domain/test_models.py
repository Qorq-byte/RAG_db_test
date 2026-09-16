from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ragdb.domain.enums import RetrievalRoute, SourceStatus, SourceType, TaskStatus
from ragdb.domain.models import (
    Chunk,
    Collection,
    Document,
    DocumentUnit,
    IngestionTask,
    SearchHit,
    Source,
    SourcePosition,
    utc_now,
)


CONTENT_HASH = "a" * 64


def test_collection_normalizes_name_and_is_frozen() -> None:
    collection = Collection(name="  深度学习  ")

    assert collection.name == "深度学习"
    with pytest.raises(ValidationError):
        collection.name = "机器学习"  # type: ignore[misc]


def test_collection_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        Collection(name="   ")


def test_source_requires_sha256_hash() -> None:
    with pytest.raises(ValidationError):
        Source(
            collection_id=uuid4(),
            source_type=SourceType.PDF,
            title="论文",
            uri="paper.pdf",
            content_hash="not-a-hash",
        )


def test_source_serializes_string_enums() -> None:
    source = Source(
        collection_id=uuid4(),
        source_type=SourceType.MARKDOWN,
        title="课程笔记",
        uri="notes.md",
        content_hash=CONTENT_HASH,
        status=SourceStatus.READY,
    )

    dumped = source.model_dump(mode="json")
    assert dumped["source_type"] == "markdown"
    assert dumped["status"] == "ready"


def test_source_position_validates_line_range() -> None:
    with pytest.raises(ValidationError):
        SourcePosition(line_start=20, line_end=10)

    with pytest.raises(ValidationError):
        SourcePosition(line_end=10)


def test_document_requires_at_least_one_unit() -> None:
    with pytest.raises(ValidationError):
        Document(source_id=uuid4(), title="空文档", units=())


def test_chunk_preserves_source_location() -> None:
    collection_id = uuid4()
    source_id = uuid4()
    document = Document(
        source_id=source_id,
        title="Transformer",
        units=(
            DocumentUnit(
                text="Self-attention content",
                position=SourcePosition(page=3, heading_path=("注意力",)),
            ),
        ),
    )
    chunk = Chunk(
        id="chunk-1",
        collection_id=collection_id,
        source_id=document.source_id,
        source_content_hash=CONTENT_HASH,
        generation=1,
        ordinal=0,
        text=document.units[0].text,
        normalized_text=document.units[0].text.lower(),
        position=document.units[0].position,
    )

    assert chunk.position.page == 3
    assert chunk.position.heading_path == ("注意力",)


def test_ingestion_task_reports_processed_count() -> None:
    task = IngestionTask(
        collection_id=uuid4(),
        status=TaskStatus.COMPLETED,
        succeeded=2,
        updated=1,
        skipped=3,
        failed=1,
    )

    assert task.processed_count == 7


def test_ingestion_task_rejects_invalid_finish_time() -> None:
    started_at = utc_now()
    with pytest.raises(ValidationError):
        IngestionTask(
            collection_id=uuid4(),
            started_at=started_at,
            finished_at=started_at - timedelta(seconds=1),
        )


def test_search_hit_requires_a_retrieval_route() -> None:
    with pytest.raises(ValidationError):
        SearchHit(
            rank=1,
            chunk_id="chunk-1",
            source_id=uuid4(),
            source_title="论文",
            source_uri="paper.pdf",
            text="content",
            routes=(),
        )

    hit = SearchHit(
        rank=1,
        chunk_id="chunk-1",
        source_id=uuid4(),
        source_title="论文",
        source_uri="paper.pdf",
        text="content",
        routes=(RetrievalRoute.VECTOR, RetrievalRoute.KEYWORD),
    )
    assert hit.routes == (RetrievalRoute.VECTOR, RetrievalRoute.KEYWORD)
