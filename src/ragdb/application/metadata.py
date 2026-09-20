"""Controlled source metadata used by ingestion and retrieval."""

from __future__ import annotations

from datetime import date
import unicodedata

from pydantic import JsonValue

CONTROLLED_METADATA_KEYS = frozenset({"tags", "course", "author", "date"})


def normalize_text(value: str, field: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError(f"{field} 不能为空")
    return normalized.casefold()


def build_ingestion_metadata(
    *, tags: tuple[str, ...] = (), course: str | None = None,
    author: str | None = None, source_date: str | None = None,
) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {}
    if tags:
        metadata["tags"] = sorted({normalize_text(tag, "标签") for tag in tags})
    if course is not None:
        metadata["course"] = normalize_text(course, "课程")
    if author is not None:
        metadata["author"] = normalize_text(author, "作者")
    if source_date is not None:
        try:
            metadata["date"] = date.fromisoformat(source_date).isoformat()
        except ValueError as exc:
            raise ValueError("日期必须为 YYYY-MM-DD") from exc
    return metadata
