"""SQLite FTS5 keyword index with mixed Chinese/English normalization."""

import re
from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import JsonValue

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.models import Chunk, RetrievedChunk
from ragdb.infrastructure.database.repository import (
    SQLiteDatabase,
    _chunk_from_row,
)


_QUERY_PARTS = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]+")


def normalize_for_fts(text: str) -> str:
    parts: list[str] = []
    for match in _QUERY_PARTS.finditer(text.lower()):
        value = match.group(0)
        if value[0].isascii():
            parts.append(value)
        else:
            parts.extend(value)
    return " ".join(parts)


def build_match_query(query: str) -> str:
    expressions: list[str] = []
    for match in _QUERY_PARTS.finditer(query.lower()):
        value = match.group(0)
        normalized = value if value[0].isascii() else " ".join(value)
        expressions.append(f'"{normalized.replace(chr(34), chr(34) * 2)}"')
    return " AND ".join(expressions)


class SQLiteKeywordIndex:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def index(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        chunk_ids = [chunk.id for chunk in chunks]
        placeholders = ",".join("?" for _ in chunk_ids)
        with self.database.connect() as connection:
            connection.execute(
                f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )
            source_titles = {
                row["id"]: row["title"]
                for row in connection.execute(
                    f"""
                    SELECT id, title FROM sources
                    WHERE id IN ({','.join('?' for _ in {str(c.source_id) for c in chunks})})
                    """,
                    list({str(chunk.source_id) for chunk in chunks}),
                ).fetchall()
            }
            connection.executemany(
                """
                INSERT INTO chunks_fts (
                    chunk_id, collection_id, source_id, generation,
                    title, text, search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        str(chunk.collection_id),
                        str(chunk.source_id),
                        chunk.generation,
                        source_titles.get(str(chunk.source_id), ""),
                        chunk.text,
                        normalize_for_fts(
                            f"{source_titles.get(str(chunk.source_id), '')} {chunk.text}"
                        ),
                    )
                    for chunk in chunks
                ],
            )

    def search(
        self,
        collection_id: UUID,
        query: str,
        limit: int,
        filters: Mapping[str, JsonValue] | None = None,
    ) -> Sequence[RetrievedChunk]:
        match_query = build_match_query(query)
        if not match_query or limit < 1:
            return []

        conditions = ["chunks_fts MATCH ?", "f.collection_id = ?"]
        parameters: list[object] = [match_query, str(collection_id)]
        if filters:
            supported_filters = {
                "source_id": "c.source_id",
                "generation": "c.generation",
                "source_type": "s.source_type",
            }
            for key, value in filters.items():
                column = supported_filters.get(key)
                if column is not None:
                    conditions.append(f"{column} = ?")
                    parameters.append(value)
                elif key == "tags" and isinstance(value, list):
                    for tag in value:
                        conditions.append("EXISTS (SELECT 1 FROM json_each(c.metadata_json, '$.tags') WHERE value = ?)")
                        parameters.append(tag)
                elif key in {"course", "author"}:
                    conditions.append(f"json_extract(c.metadata_json, '$.{key}') = ?")
                    parameters.append(value)
                elif key == "date_from":
                    conditions.append("json_extract(c.metadata_json, '$.date') >= ?")
                    parameters.append(value)
                elif key == "date_to":
                    conditions.append("json_extract(c.metadata_json, '$.date') <= ?")
                    parameters.append(value)
        parameters.append(limit)

        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, bm25(chunks_fts) AS keyword_score
                FROM chunks_fts AS f
                JOIN chunks AS c ON c.id = f.chunk_id
                JOIN sources AS s ON s.id = c.source_id
                WHERE {' AND '.join(conditions)}
                ORDER BY keyword_score ASC, c.id ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            RetrievedChunk(
                chunk=_chunk_from_row(row),
                score=float(row["keyword_score"]),
                route=RetrievalRoute.KEYWORD,
            )
            for row in rows
        ]

    def delete_source_generation(
        self,
        collection_id: UUID,
        source_id: UUID,
        generation: int,
    ) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM chunks_fts
                WHERE collection_id = ? AND source_id = ? AND generation = ?
                """,
                (str(collection_id), str(source_id), generation),
            )
        return cursor.rowcount
