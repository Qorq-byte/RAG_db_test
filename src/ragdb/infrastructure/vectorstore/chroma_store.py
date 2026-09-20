"""Persistent ChromaDB adapter for chunk embeddings."""

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias
from uuid import UUID

import chromadb
from chromadb.api.models.Collection import Collection as ChromaCollection
from chromadb.config import Settings
from chromadb.errors import ChromaError, NotFoundError
from pydantic import JsonValue

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.errors import StorageError
from ragdb.domain.models import Chunk, RetrievedChunk, SourcePosition


ChromaScalar: TypeAlias = str | int | float | bool
ChromaMetadataValue: TypeAlias = ChromaScalar | list[ChromaScalar]
ChromaMetadata: TypeAlias = dict[str, ChromaMetadataValue]
ChromaWhere: TypeAlias = dict[str, object]

_POSITION_JSON_KEY = "_ragdb_position_json"
_METADATA_JSON_KEY = "_ragdb_metadata_json"
_NORMALIZED_TEXT_KEY = "_ragdb_normalized_text"
_USER_METADATA_PREFIX = "meta__"
_RESERVED_FILTER_FIELDS = {
    "collection_id",
    "source_id",
    "source_content_hash",
    "generation",
    "ordinal",
}
_SCALAR_FILTER_OPERATORS = {
    "$eq",
    "$ne",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$contains",
    "$not_contains",
}
_LIST_FILTER_OPERATORS = {"$in", "$nin"}


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_scalar(value: object) -> bool:
    return isinstance(value, (str, int, float, bool))


def _filterable_metadata_value(value: JsonValue) -> ChromaMetadataValue | None:
    if _is_scalar(value):
        return value
    if not isinstance(value, list) or not value:
        return None
    if not all(_is_scalar(item) for item in value):
        return None

    first_type = type(value[0])
    if all(type(item) is first_type for item in value):
        return list(value)
    if first_type in {int, float} and all(type(item) in {int, float} for item in value):
        return [float(item) for item in value]
    return None


def _chunk_metadata(chunk: Chunk) -> ChromaMetadata:
    metadata: ChromaMetadata = {
        "collection_id": str(chunk.collection_id),
        "source_id": str(chunk.source_id),
        "source_content_hash": chunk.source_content_hash,
        "generation": chunk.generation,
        "ordinal": chunk.ordinal,
        _POSITION_JSON_KEY: _dump_json(chunk.position.model_dump(mode="json")),
        _METADATA_JSON_KEY: _dump_json(chunk.metadata),
        _NORMALIZED_TEXT_KEY: chunk.normalized_text,
    }
    for key, value in chunk.metadata.items():
        filterable = _filterable_metadata_value(value)
        if filterable is not None:
            metadata[f"{_USER_METADATA_PREFIX}{key}"] = filterable
    return metadata


def _chunk_from_chroma(
    chunk_id: str,
    document: str | None,
    metadata: Mapping[str, object] | None,
) -> Chunk:
    if document is None or metadata is None:
        raise StorageError(f"ChromaDB 中的切片记录不完整：{chunk_id}")
    try:
        position_raw = metadata[_POSITION_JSON_KEY]
        custom_metadata_raw = metadata[_METADATA_JSON_KEY]
        normalized_text = metadata[_NORMALIZED_TEXT_KEY]
        if not all(
            isinstance(value, str)
            for value in (position_raw, custom_metadata_raw, normalized_text)
        ):
            raise TypeError("serialized metadata must be strings")
        custom_metadata = json.loads(custom_metadata_raw)
        if not isinstance(custom_metadata, dict):
            raise TypeError("chunk metadata must be an object")
        return Chunk(
            id=chunk_id,
            collection_id=UUID(str(metadata["collection_id"])),
            source_id=UUID(str(metadata["source_id"])),
            source_content_hash=str(metadata["source_content_hash"]),
            generation=int(metadata["generation"]),
            ordinal=int(metadata["ordinal"]),
            text=document,
            normalized_text=normalized_text,
            position=SourcePosition.model_validate_json(position_raw),
            metadata=custom_metadata,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StorageError(f"无法读取 ChromaDB 切片记录：{chunk_id}") from exc


def _filter_field(key: str) -> str:
    if key in _RESERVED_FILTER_FIELDS:
        return key
    if key.startswith("metadata."):
        key = key.removeprefix("metadata.")
    return f"{_USER_METADATA_PREFIX}{key}"


def _filter_expression(key: str, value: JsonValue) -> object:
    if _is_scalar(value):
        return value
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError(f"不支持的元数据筛选值：{key}")

    operator, operand = next(iter(value.items()))
    if operator in _SCALAR_FILTER_OPERATORS and _is_scalar(operand):
        return {operator: operand}
    if operator in _LIST_FILTER_OPERATORS:
        filterable = _filterable_metadata_value(operand)
        if isinstance(filterable, list):
            return {operator: filterable}
    raise ValueError(f"不支持的元数据筛选值：{key}")


def _build_where(filters: Mapping[str, JsonValue] | None) -> ChromaWhere | None:
    if not filters:
        return None
    clauses: list[ChromaWhere] = []
    for key, value in filters.items():
        if key in {"$and", "$or"}:
            raise ValueError("filters 不接受顶层逻辑运算符")
        if value is None:
            raise ValueError(f"不支持的元数据筛选值：{key}")
        clauses.append({_filter_field(key): _filter_expression(key, value)})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class ChromaVectorStore:
    """Store externally generated embeddings in a persistent Chroma database."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self._client = chromadb.PersistentClient(
                path=self.directory,
                settings=Settings(anonymized_telemetry=False),
            )
        except ChromaError as exc:
            raise StorageError("初始化 ChromaDB 失败") from exc

    @staticmethod
    def collection_name(collection_id: UUID) -> str:
        return f"ragdb_{collection_id.hex}"

    def _get_collection(self, collection_id: UUID) -> ChromaCollection | None:
        try:
            return self._client.get_collection(
                name=self.collection_name(collection_id),
                embedding_function=None,
            )
        except NotFoundError:
            return None
        except ChromaError as exc:
            raise StorageError("读取 ChromaDB 集合失败") from exc

    def _get_or_create_collection(self, collection_id: UUID) -> ChromaCollection:
        try:
            return self._client.get_or_create_collection(
                name=self.collection_name(collection_id),
                embedding_function=None,
                metadata={"ragdb_collection_id": str(collection_id)},
            )
        except ChromaError as exc:
            raise StorageError("创建 ChromaDB 集合失败") from exc

    def upsert(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("切片数量与向量数量不一致")
        if not chunks:
            return
        if len({chunk.id for chunk in chunks}) != len(chunks):
            raise ValueError("同一批次中存在重复的切片 ID")

        dimensions = {len(embedding) for embedding in embeddings}
        if 0 in dimensions or len(dimensions) != 1:
            raise ValueError("同一批次的向量必须非空且维度一致")

        grouped: dict[UUID, list[tuple[Chunk, Sequence[float]]]] = defaultdict(list)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            grouped[chunk.collection_id].append((chunk, embedding))

        batch_size = self._client.get_max_batch_size()
        try:
            for collection_id, records in grouped.items():
                collection = self._get_or_create_collection(collection_id)
                for start in range(0, len(records), batch_size):
                    batch = records[start : start + batch_size]
                    collection.upsert(
                        ids=[chunk.id for chunk, _ in batch],
                        embeddings=[list(embedding) for _, embedding in batch],
                        documents=[chunk.text for chunk, _ in batch],
                        metadatas=[_chunk_metadata(chunk) for chunk, _ in batch],
                    )
        except ChromaError as exc:
            raise StorageError("写入 ChromaDB 向量失败") from exc

    def search(
        self,
        collection_id: UUID,
        query_embedding: Sequence[float],
        limit: int,
        filters: Mapping[str, JsonValue] | None = None,
    ) -> Sequence[RetrievedChunk]:
        if limit < 1:
            return []
        if not query_embedding:
            raise ValueError("查询向量不能为空")

        collection = self._get_collection(collection_id)
        if collection is None:
            return []
        try:
            count = collection.count()
            if count == 0:
                return []
            result = collection.query(
                query_embeddings=[list(query_embedding)],
                n_results=min(limit, count),
                where=_build_where(filters),
                include=["documents", "metadatas", "distances"],
            )
        except ChromaError as exc:
            raise StorageError("查询 ChromaDB 向量失败") from exc

        ids = result["ids"][0]
        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []
        if not (len(ids) == len(documents) == len(metadatas) == len(distances)):
            raise StorageError("ChromaDB 查询结果字段长度不一致")

        return [
            RetrievedChunk(
                chunk=_chunk_from_chroma(chunk_id, document, metadata),
                score=1.0 / (1.0 + max(float(distance), 0.0)),
                route=RetrievalRoute.VECTOR,
            )
            for chunk_id, document, metadata, distance in zip(
                ids,
                documents,
                metadatas,
                distances,
                strict=True,
            )
        ]

    def delete_source_generation(
        self,
        collection_id: UUID,
        source_id: UUID,
        generation: int,
    ) -> int:
        collection = self._get_collection(collection_id)
        if collection is None:
            return 0
        where: ChromaWhere = {
            "$and": [
                {"source_id": str(source_id)},
                {"generation": generation},
            ]
        }
        try:
            existing = collection.get(where=where, include=[])
            ids = existing["ids"]
            if not ids:
                return 0
            collection.delete(ids=ids)
            return len(ids)
        except ChromaError as exc:
            raise StorageError("删除 ChromaDB 资料代次失败") from exc

    def delete_stale_source_generations(
        self,
        collection_id: UUID,
        source_id: UUID,
        current_generation: int,
    ) -> int:
        """Remove vectors left by an interrupted generation switch."""
        collection = self._get_collection(collection_id)
        if collection is None:
            return 0
        try:
            records = collection.get(where={"source_id": str(source_id)}, include=["metadatas"])
            ids = [
                chunk_id for chunk_id, metadata in zip(records["ids"], records["metadatas"], strict=True)
                if metadata is not None and int(metadata["generation"]) != current_generation
            ]
            if ids:
                collection.delete(ids=ids)
            return len(ids)
        except ChromaError as exc:
            raise StorageError("清理 ChromaDB 孤立资料代次失败") from exc

    def delete_collection(self, collection_id: UUID) -> None:
        try:
            self._client.delete_collection(name=self.collection_name(collection_id))
        except NotFoundError:
            return
        except ChromaError as exc:
            raise StorageError("删除 ChromaDB 集合失败") from exc
