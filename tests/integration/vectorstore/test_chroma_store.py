from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.models import Chunk, SourcePosition
from ragdb.domain.ports import VectorStore
from ragdb.infrastructure.vectorstore.chroma_store import ChromaVectorStore


CONTENT_HASH = "a" * 64


def make_chunk(
    *,
    chunk_id: str,
    collection_id: UUID,
    source_id: UUID,
    generation: int = 1,
    ordinal: int = 0,
    text: str = "测试文本",
    metadata: dict[str, object] | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        collection_id=collection_id,
        source_id=source_id,
        source_content_hash=CONTENT_HASH,
        generation=generation,
        ordinal=ordinal,
        text=text,
        normalized_text=text.lower(),
        position=SourcePosition(page=1, heading_path=("章节",)),
        metadata=metadata or {},
    )


def open_store(tmp_path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(tmp_path / "chroma")


def test_store_implements_vector_store_protocol(tmp_path: Path) -> None:
    assert isinstance(open_store(tmp_path), VectorStore)


def test_collection_name_uses_stable_uuid() -> None:
    collection_id = UUID("12345678-1234-5678-1234-567812345678")

    assert (
        ChromaVectorStore.collection_name(collection_id)
        == "ragdb_12345678123456781234567812345678"
    )


def test_upsert_search_and_persist_chunks(tmp_path: Path) -> None:
    collection_id = uuid4()
    source_id = uuid4()
    chunks = [
        make_chunk(
            chunk_id="closest",
            collection_id=collection_id,
            source_id=source_id,
            text="Alpha",
            metadata={"course": "AI", "tags": ["rag", "vector"]},
        ),
        make_chunk(
            chunk_id="farther",
            collection_id=collection_id,
            source_id=source_id,
            ordinal=1,
            text="Beta",
            metadata={"course": "AI"},
        ),
    ]
    store = open_store(tmp_path)
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])

    reopened = open_store(tmp_path)
    results = reopened.search(collection_id, [1.0, 0.0], limit=10)

    assert [result.chunk.id for result in results] == ["closest", "farther"]
    assert results[0].score > results[1].score
    assert results[0].route is RetrievalRoute.VECTOR
    assert results[0].chunk.text == "Alpha"
    assert results[0].chunk.normalized_text == "alpha"
    assert results[0].chunk.position.heading_path == ("章节",)
    assert results[0].chunk.metadata == {
        "course": "AI",
        "tags": ["rag", "vector"],
    }


def test_upsert_is_idempotent_and_collections_are_isolated(tmp_path: Path) -> None:
    first_collection = uuid4()
    second_collection = uuid4()
    source_id = uuid4()
    first = make_chunk(
        chunk_id="shared-id",
        collection_id=first_collection,
        source_id=source_id,
        text="first",
    )
    updated = first.model_copy(update={"text": "updated", "normalized_text": "updated"})
    second = make_chunk(
        chunk_id="shared-id",
        collection_id=second_collection,
        source_id=source_id,
        text="second",
    )
    store = open_store(tmp_path)

    store.upsert([first], [[1.0, 0.0]])
    store.upsert([updated], [[1.0, 0.0]])
    store.upsert([second], [[0.0, 1.0]])

    assert store.search(first_collection, [1.0, 0.0], 5)[0].chunk.text == "updated"
    assert store.search(second_collection, [0.0, 1.0], 5)[0].chunk.text == "second"


def test_search_applies_scalar_metadata_filters(tmp_path: Path) -> None:
    collection_id = uuid4()
    source_id = uuid4()
    store = open_store(tmp_path)
    store.upsert(
        [
            make_chunk(
                chunk_id="ai",
                collection_id=collection_id,
                source_id=source_id,
                metadata={"course": "AI"},
            ),
            make_chunk(
                chunk_id="math",
                collection_id=collection_id,
                source_id=source_id,
                ordinal=1,
                metadata={"course": "Math"},
            ),
        ],
        [[1.0, 0.0], [0.9, 0.1]],
    )

    results = store.search(
        collection_id,
        [1.0, 0.0],
        limit=10,
        filters={"course": "Math"},
    )

    assert [result.chunk.id for result in results] == ["math"]


def test_search_applies_array_metadata_filters(tmp_path: Path) -> None:
    collection_id = uuid4()
    source_id = uuid4()
    store = open_store(tmp_path)
    store.upsert(
        [
            make_chunk(
                chunk_id="rag",
                collection_id=collection_id,
                source_id=source_id,
                metadata={"tags": ["rag", "vector"]},
            ),
            make_chunk(
                chunk_id="vision",
                collection_id=collection_id,
                source_id=source_id,
                ordinal=1,
                metadata={"tags": ["vision"]},
            ),
        ],
        [[1.0, 0.0], [0.9, 0.1]],
    )

    results = store.search(
        collection_id,
        [1.0, 0.0],
        limit=10,
        filters={"tags": {"$contains": "rag"}},
    )

    assert [result.chunk.id for result in results] == ["rag"]


def test_delete_source_generation_is_precise(tmp_path: Path) -> None:
    collection_id = uuid4()
    source_id = uuid4()
    other_source_id = uuid4()
    store = open_store(tmp_path)
    chunks = [
        make_chunk(
            chunk_id="old",
            collection_id=collection_id,
            source_id=source_id,
            generation=1,
        ),
        make_chunk(
            chunk_id="current",
            collection_id=collection_id,
            source_id=source_id,
            generation=2,
            ordinal=1,
        ),
        make_chunk(
            chunk_id="other",
            collection_id=collection_id,
            source_id=other_source_id,
            generation=1,
            ordinal=2,
        ),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]])

    assert store.delete_source_generation(collection_id, source_id, 1) == 1
    assert store.delete_source_generation(collection_id, source_id, 1) == 0
    remaining = store.search(collection_id, [1.0, 0.0], limit=10)

    assert {result.chunk.id for result in remaining} == {"current", "other"}


def test_delete_collection_is_idempotent(tmp_path: Path) -> None:
    collection_id = uuid4()
    chunk = make_chunk(
        chunk_id="chunk",
        collection_id=collection_id,
        source_id=uuid4(),
    )
    store = open_store(tmp_path)
    store.upsert([chunk], [[1.0, 0.0]])

    store.delete_collection(collection_id)
    store.delete_collection(collection_id)

    assert store.search(collection_id, [1.0, 0.0], limit=5) == []


@pytest.mark.parametrize(
    ("chunks", "embeddings", "message"),
    [
        ("one", [], "数量不一致"),
        ("one", [[]], "非空且维度一致"),
        ("two", [[1.0], [1.0, 2.0]], "非空且维度一致"),
    ],
)
def test_upsert_validates_batch_shape(
    tmp_path: Path,
    chunks: str,
    embeddings: list[list[float]],
    message: str,
) -> None:
    collection_id = uuid4()
    source_id = uuid4()
    one = make_chunk(
        chunk_id="one", collection_id=collection_id, source_id=source_id
    )
    batch = [one]
    if chunks == "two":
        batch.append(
            make_chunk(
                chunk_id="two",
                collection_id=collection_id,
                source_id=source_id,
                ordinal=1,
            )
        )

    with pytest.raises(ValueError, match=message):
        open_store(tmp_path).upsert(batch, embeddings)
