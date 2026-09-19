"""Select the appropriate structure-aware chunker for a parsed document."""

from uuid import UUID

from ragdb.config import ChunkingSettings
from ragdb.domain.models import Chunk, Document
from ragdb.infrastructure.chunking.code import CodeChunker
from ragdb.infrastructure.chunking.text import TextChunker


class StructuredChunker:
    def __init__(self, settings: ChunkingSettings | None = None) -> None:
        settings = settings or ChunkingSettings()
        self.text = TextChunker(settings.max_characters, settings.overlap_characters)
        self.code = CodeChunker(settings.max_characters, settings.overlap_characters)

    def chunk(
        self,
        document: Document,
        collection_id: UUID,
        source_content_hash: str,
        generation: int,
    ) -> tuple[Chunk, ...]:
        is_code = document.metadata.get("format") == "code" or any(
            "language" in unit.metadata for unit in document.units
        )
        chunker = self.code if is_code else self.text
        return chunker.chunk(
            document,
            collection_id,
            source_content_hash,
            generation,
        )
