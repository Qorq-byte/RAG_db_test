"""Heading-, page-, paragraph-, and sentence-aware text chunking."""

from uuid import UUID

from ragdb.domain.models import Chunk, Document
from ragdb.infrastructure.chunking._common import Fragment, build_chunks


class TextChunker:
    name = "structured_text"

    def __init__(self, max_characters: int = 1200, overlap_characters: int = 200) -> None:
        _validate_sizes(max_characters, overlap_characters)
        self.max_characters = max_characters
        self.overlap_characters = overlap_characters

    def chunk(
        self,
        document: Document,
        collection_id: UUID,
        source_content_hash: str,
        generation: int,
    ) -> tuple[Chunk, ...]:
        fragments = [
            Fragment(
                text=unit.text,
                position=unit.position,
                metadata=dict(unit.metadata),
                boundary_key=(
                    unit.position.page,
                    unit.position.slide,
                    unit.position.heading_path,
                ),
            )
            for unit in document.units
        ]
        return build_chunks(
            document=document,
            fragments=fragments,
            collection_id=collection_id,
            source_content_hash=source_content_hash,
            generation=generation,
            max_characters=self.max_characters,
            overlap_characters=self.overlap_characters,
            chunker_name=self.name,
        )


def _validate_sizes(max_characters: int, overlap_characters: int) -> None:
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    if overlap_characters < 0:
        raise ValueError("overlap_characters must not be negative")
    if overlap_characters >= max_characters:
        raise ValueError("overlap_characters must be smaller than max_characters")
