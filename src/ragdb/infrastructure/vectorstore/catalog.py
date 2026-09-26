"""Enumerate existing Chroma collections without creating an empty database."""

from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path

from chromadb.errors import ChromaError

from ragdb.domain.errors import ConflictError, StorageError
from ragdb.infrastructure.vectorstore.clients import open_client, close_client


@dataclass(frozen=True)
class VectorCollectionSnapshot:
    name: str
    storage_id: str
    metadata: dict
    vector_count: int


class ChromaIndexCatalog:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._opened_client = None

    @contextmanager
    def session(self):
        try:
            yield self
        finally:
            client, self._opened_client = self._opened_client, None
            if client is not None:
                close_client(client)

    def _client(self):
        if not (self.directory / "chroma.sqlite3").is_file():
            raise StorageError("向量数据库已不存在，请重新预览并核对存储目录。")
        if self._opened_client is None:
            self._opened_client = open_client(self.directory)
        return self._opened_client

    def snapshot(self) -> tuple[VectorCollectionSnapshot, ...]:
        if not self.directory.exists():
            return ()
        if not self.directory.is_dir():
            raise StorageError("向量存储路径不是目录。")
        if not (self.directory / "chroma.sqlite3").is_file():
            if any(self.directory.iterdir()):
                raise StorageError("向量目录中缺少 Chroma 数据库，请核对存储路径。")
            return ()
        try:
            client = self._client()
            result = []
            for collection in client.list_collections():
                result.append(VectorCollectionSnapshot(
                    name=collection.name,
                    storage_id=str(collection.id),
                    metadata=dict(collection.metadata or {}),
                    vector_count=collection.count(),
                ))
            return tuple(sorted(result, key=lambda item: item.name))
        except (ChromaError, ValueError, OSError) as exc:
            raise StorageError("读取向量索引清单失败，请稍后重试并检查存储目录。") from exc

    def delete_checked(self, name: str, storage_id: str, collection_id: str, vector_count: int) -> None:
        """Delete one previously authorized object, never a same-name replacement."""
        try:
            client = self._client()
            collection = client.get_collection(name=name, embedding_function=None)
            if (str(collection.id) != storage_id
                    or (collection.metadata or {}).get("ragdb_collection_id") != collection_id
                    or collection.count() != vector_count):
                raise ConflictError("目标索引已变化，请重新预览。")
            client.delete_collection(name=name)
        except (ChromaError, ValueError, OSError) as exc:
            raise StorageError("删除旧向量索引失败，请重新预览后重试。") from exc

    def verify_queryable(self, name: str, storage_id: str) -> None:
        """Confirm active indexes can serve queries before discarding older copies."""
        try:
            collection = self._client().get_collection(name=name, embedding_function=None)
            if str(collection.id) != storage_id:
                raise ConflictError("活动索引身份已变化，请重新预览。")
            if collection.count() == 0:
                return
            sample = collection.get(limit=1, include=["embeddings"])
            embeddings = sample.get("embeddings")
            if embeddings is None or len(embeddings) != 1:
                raise StorageError("活动索引缺少可验证的向量，未执行清理。")
            result = collection.query(query_embeddings=[embeddings[0]], n_results=1, include=[])
            if not result["ids"] or not result["ids"][0]:
                raise StorageError("活动索引无法返回查询结果，未执行清理。")
        except (ChromaError, ValueError, OSError) as exc:
            raise StorageError("活动索引暂时无法检索，未执行清理；请核对索引或稍后重试。") from exc
