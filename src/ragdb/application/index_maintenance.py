"""Inspect inactive vector collections and bind a preview to its exact targets."""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from ragdb.domain.errors import ConflictError, StorageError
from ragdb.infrastructure.database import SQLiteCollectionRepository, SQLiteDatabase, SQLiteEmbeddingProfileRepository
from ragdb.infrastructure.vectorstore.catalog import ChromaIndexCatalog
from ragdb.infrastructure.vectorstore.chroma_store import ChromaVectorStore


_INDEX_NAME = re.compile(r"ragdb_([a-f0-9]{32})(?:_([a-f0-9]{24}))?\Z")


@dataclass(frozen=True)
class IndexInventoryItem:
    name: str
    collection_id: UUID | None
    collection_name: str | None
    namespace: str | None
    vector_count: int
    state: str
    reason: str
    storage_id: str = ""


@dataclass(frozen=True)
class IndexInventory:
    preview_id: str
    active_fingerprint: str
    active_namespace: str
    items: tuple[IndexInventoryItem, ...]

    @property
    def candidates(self) -> tuple[IndexInventoryItem, ...]:
        return tuple(item for item in self.items if item.state == "stale")


class IndexMaintenanceService:
    def __init__(self, database: SQLiteDatabase, chroma_directory: Path) -> None:
        self.database = database
        self.chroma_directory = chroma_directory
        self.profiles = SQLiteEmbeddingProfileRepository(database)
        self.collections = SQLiteCollectionRepository(database)
        self.catalog = ChromaIndexCatalog(chroma_directory)

    def preview(self) -> IndexInventory:
        if not self.database.path.is_file():
            raise StorageError("尚未初始化知识库，请先打开工作台或创建知识集合。")
        active = self.profiles.get()
        if active is None:
            raise StorageError("尚未初始化活动嵌入索引，请先打开工作台或创建知识集合。")
        _, fingerprint, namespace = active
        collections = {item.id: item.name for item in self.collections.list_all()}
        items = []
        for stored in self.catalog.snapshot():
            match = _INDEX_NAME.fullmatch(stored.name)
            collection_id = UUID(hex=match[1]) if match else None
            collection_name = collections.get(collection_id)
            index_namespace = (match[2] or "legacy") if match else None
            state, reason = "unknown", "名称不符合项目索引规则，需人工核查。"
            if match:
                # Protect an active name even if its ownership metadata is damaged.
                if stored.name == ChromaVectorStore.collection_name(collection_id, namespace):
                    state, reason = "active", "当前活动索引，禁止清理。"
                elif collection_id not in collections:
                    reason = "SQLite 中没有对应知识集合，需人工核查。"
                elif stored.metadata.get("ragdb_collection_id") != str(collection_id):
                    reason = "归属元数据缺失或不匹配，需人工核查。"
                else:
                    state, reason = "stale", "已停用且归属已确认，可在确认后清理。"
            items.append(IndexInventoryItem(
                stored.name, collection_id, collection_name, index_namespace,
                stored.vector_count, state, reason, stored.storage_id,
            ))
        if self.profiles.get() != active or {
            item.id: item.name for item in self.collections.list_all()
        } != collections:
            raise ConflictError("盘点期间索引或集合发生变化，请重新预览。")
        payload = {
            "version": 1,
            "database": str(self.database.path.resolve()),
            "chroma": str(self.chroma_directory.resolve()),
            "active": [fingerprint, namespace],
            "collections": sorted((str(key), value) for key, value in collections.items()),
            "items": [asdict(item) for item in items],
        }
        preview_id = hashlib.sha256(json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")).hexdigest()
        return IndexInventory(preview_id, fingerprint, namespace, tuple(items))
