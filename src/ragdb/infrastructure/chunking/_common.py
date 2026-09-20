"""Shared chunk construction and boundary helpers."""

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from ragdb.domain.models import Chunk, Document, SourcePosition


@dataclass(frozen=True, slots=True)
class Fragment:
    text: str
    position: SourcePosition
    metadata: dict
    boundary_key: tuple


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return " ".join(normalized.split()).casefold()


def split_at_natural_boundaries(text: str, max_characters: int) -> list[str]:
    """Split oversized text at paragraph, sentence, then hard character boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_characters:
        return [text]

    atoms = [
        atom.strip()
        for atom in re.split(r"\n{2,}|(?<=[。！？.!?；;])\s*", text)
        if atom.strip()
    ]
    pieces: list[str] = []
    current = ""
    for atom in atoms:
        separator = "\n\n" if "\n" in atom or "\n" in current else " "
        candidate = atom if not current else current + separator + atom
        if len(candidate) <= max_characters:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        while len(atom) > max_characters:
            cut = _preferred_cut(atom, max_characters)
            pieces.append(atom[:cut].rstrip())
            atom = atom[cut:].lstrip()
        current = atom
    if current:
        pieces.append(current)
    return pieces


def _preferred_cut(text: str, limit: int) -> int:
    window = text[:limit]
    candidates = [
        window.rfind(marker)
        for marker in ("\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", " ", "，", ",")
    ]
    cut = max(candidates)
    return cut + 1 if cut >= limit // 2 else limit


def build_chunks(
    *,
    document: Document,
    fragments: Sequence[Fragment],
    collection_id: UUID,
    source_content_hash: str,
    generation: int,
    max_characters: int,
    overlap_characters: int,
    chunker_name: str,
) -> tuple[Chunk, ...]:
    drafts: list[tuple[str, SourcePosition, dict]] = []
    grouped: list[tuple[str, SourcePosition, dict, tuple]] = []
    for fragment in fragments:
        text = fragment.text.strip()
        if not text:
            continue
        if grouped and grouped[-1][3] == fragment.boundary_key:
            previous_text, position, metadata, key = grouped[-1]
            grouped[-1] = (previous_text + "\n\n" + text, position, metadata, key)
        else:
            grouped.append((text, fragment.position, fragment.metadata.copy(), fragment.boundary_key))

    for text, position, metadata, _ in grouped:
        for piece in _split_with_overlap(text, max_characters, overlap_characters):
            drafts.append((piece, position, metadata.copy()))

    chunks: list[Chunk] = []
    for ordinal, (text, position, metadata) in enumerate(drafts):
        chunk_metadata = {
            **document.metadata,
            **metadata,
            "chunker": chunker_name,
            "max_characters": max_characters,
            "overlap_characters": overlap_characters,
        }
        chunk_id = stable_chunk_id(
            document.source_id,
            source_content_hash,
            generation,
            ordinal,
            position,
            text,
            max_characters,
            overlap_characters,
            chunker_name,
        )
        chunks.append(
            Chunk(
                id=chunk_id,
                collection_id=collection_id,
                source_id=document.source_id,
                source_content_hash=source_content_hash,
                generation=generation,
                ordinal=ordinal,
                text=text,
                normalized_text=normalize_text(text),
                position=position,
                metadata=chunk_metadata,
            )
        )
    return tuple(chunks)


def _split_with_overlap(text: str, limit: int, overlap: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        remaining = text[start:]
        if len(remaining) <= limit:
            tail = remaining.strip()
            if tail:
                pieces.append(tail)
            break
        cut = _preferred_cut(remaining, limit)
        piece = remaining[:cut].strip()
        if piece:
            pieces.append(piece)
        next_start = start + cut - overlap
        if next_start <= start:
            next_start = start + cut
        start = next_start
        while start < len(text) and text[start].isspace():
            start += 1
    return pieces


def stable_chunk_id(
    source_id: UUID,
    source_content_hash: str,
    generation: int,
    ordinal: int,
    position: SourcePosition,
    text: str,
    max_characters: int,
    overlap_characters: int,
    chunker_name: str,
) -> str:
    payload = {
        "source_id": str(source_id),
        "source_content_hash": source_content_hash,
        "generation": generation,
        "ordinal": ordinal,
        "position": position.model_dump(mode="json"),
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "max_characters": max_characters,
        "overlap_characters": overlap_characters,
        "chunker": chunker_name,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
