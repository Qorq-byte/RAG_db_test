"""Enumerate existing Chroma collections without creating an empty database."""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.errors import ChromaError

from ragdb.domain.errors import StorageError


@dataclass(frozen=True)
class VectorCollectionSnapshot:
    name: str
    storage_id: str
    metadata: dict
    vector_count: int


class ChromaIndexCatalog:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _client(self):
        return chromadb.PersistentClient(
            path=str(self.directory), settings=Settings(anonymized_telemetry=False)
        )

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
