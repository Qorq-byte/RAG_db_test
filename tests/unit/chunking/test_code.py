from uuid import uuid4

from ragdb.config import ChunkingSettings
from ragdb.domain.models import Document, DocumentUnit, SourcePosition
from ragdb.infrastructure.chunking.code import CodeChunker
from ragdb.infrastructure.chunking.strategy import StructuredChunker


CONTENT_HASH = "b" * 64


def python_document() -> Document:
    return Document(
        source_id=uuid4(),
        title="module.py",
        units=(
            DocumentUnit(
                text=(
                    "import os\n\n"
                    "def first():\n    return 1\n\n"
                    "class Worker:\n    def run(self):\n        return 2\n"
                ),
                position=SourcePosition(line_start=1, line_end=8),
                metadata={"language": "python"},
            ),
        ),
        metadata={"format": "code", "language": "python"},
    )


def test_code_chunker_prefers_top_level_symbols() -> None:
    chunks = CodeChunker(max_characters=100, overlap_characters=10).chunk(
        python_document(), uuid4(), CONTENT_HASH, 1
    )
    symbols = [chunk.position.code_symbol for chunk in chunks]
    assert symbols == [None, "first", "Worker"]
    assert chunks[1].position.line_start == 3
    assert chunks[2].position.line_start == 6


def test_strategy_selects_code_chunker() -> None:
    chunks = StructuredChunker(
        ChunkingSettings(max_characters=200, overlap_characters=20)
    ).chunk(python_document(), uuid4(), CONTENT_HASH, 1)
    assert all(chunk.metadata["chunker"] == "structured_code" for chunk in chunks)
