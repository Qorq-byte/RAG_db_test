from uuid import uuid4

from ragdb.domain.models import Document, DocumentUnit, SourcePosition
from ragdb.infrastructure.chunking.text import TextChunker


CONTENT_HASH = "a" * 64


def test_text_chunker_keeps_heading_boundaries_and_limits_size() -> None:
    document = Document(
        source_id=uuid4(),
        title="笔记",
        units=(
            DocumentUnit(
                text="第一句。第二句。第三句。",
                position=SourcePosition(heading_path=("第一章",)),
            ),
            DocumentUnit(
                text="另一章节的内容。",
                position=SourcePosition(heading_path=("第二章",)),
            ),
        ),
    )
    chunks = TextChunker(max_characters=12, overlap_characters=3).chunk(
        document, uuid4(), CONTENT_HASH, 1
    )

    assert all(len(chunk.text) <= 12 for chunk in chunks)
    assert chunks[0].text.endswith("。")
    assert chunks[0].position.heading_path == ("第一章",)
    assert chunks[-1].position.heading_path == ("第二章",)
    assert all(chunk.generation == 1 for chunk in chunks)


def test_text_chunker_combines_short_paragraphs_in_same_section() -> None:
    position = SourcePosition(heading_path=("同一章",))
    document = Document(
        source_id=uuid4(),
        title="笔记",
        units=(
            DocumentUnit(text="短段落一。", position=position),
            DocumentUnit(text="短段落二。", position=position),
        ),
    )
    chunks = TextChunker(max_characters=50, overlap_characters=5).chunk(
        document, uuid4(), CONTENT_HASH, 1
    )
    assert len(chunks) == 1
    assert "短段落一" in chunks[0].text and "短段落二" in chunks[0].text


def test_chunk_ids_are_stable_and_change_with_configuration() -> None:
    document = Document(
        source_id=uuid4(),
        title="稳定 ID",
        units=(DocumentUnit(text="alpha beta gamma delta"),),
    )
    collection_id = uuid4()
    first = TextChunker(20, 5).chunk(document, collection_id, CONTENT_HASH, 1)
    repeated = TextChunker(20, 5).chunk(document, collection_id, CONTENT_HASH, 2)
    changed = TextChunker(21, 5).chunk(document, collection_id, CONTENT_HASH, 1)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in repeated]
    assert first[0].id != changed[0].id
    assert first[0].normalized_text == "alpha beta gamma"


def test_text_chunker_uses_configured_overlap() -> None:
    text = "alpha bravo charlie delta echo foxtrot golf hotel"
    document = Document(source_id=uuid4(), title="重叠", units=(DocumentUnit(text=text),))
    chunks = TextChunker(max_characters=25, overlap_characters=8).chunk(
        document, uuid4(), CONTENT_HASH, 1
    )
    assert len(chunks) >= 2
    assert set(chunks[0].text.split()) & set(chunks[1].text.split())
