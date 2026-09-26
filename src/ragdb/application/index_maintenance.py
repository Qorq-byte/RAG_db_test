"""Inspect inactive vector collections and bind a preview to its exact targets."""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from ragdb.domain.errors import ConflictError, StorageError
from ragdb.domain.models import OperationLog
from ragdb.infrastructure.database import SQLiteCollectionRepository, SQLiteDatabase, SQLiteEmbeddingProfileRepository, SQLiteEmbeddingOperationGate, SQLiteOperationLogRepository
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


@dataclass(frozen=True)
class IndexCleanupResult:
    deleted: tuple[str, ...]
    remaining: tuple[str, ...]
    error: str | None = None
    audit_warning: str | None = None


class IndexMaintenanceService:
    def __init__(self, database: SQLiteDatabase, chroma_directory: Path) -> None:
        self.database = database
        self.chroma_directory = chroma_directory
        self.profiles = SQLiteEmbeddingProfileRepository(database)
        self.collections = SQLiteCollectionRepository(database)
        self.catalog = ChromaIndexCatalog(chroma_directory)

    def clean(self, preview_id: str) -> IndexCleanupResult:
        """Execute only the exact inventory explicitly confirmed by the caller."""
        if not re.fullmatch(r"[a-f0-9]{64}", preview_id):
            raise ConflictError("无效的预览标识，请先预览旧索引。")
        if not self.database.path.is_file():
            raise StorageError("知识库数据库不存在，未执行清理。")
        with self.catalog.session(), SQLiteEmbeddingOperationGate(self.database).rebuild():
            inventory = self._preview()
            if inventory.preview_id != preview_id:
                raise ConflictError("索引或集合已变化，旧预览失效，请重新预览并确认。")
            candidates = inventory.candidates
            if not candidates:
                return IndexCleanupResult((), ())
            active_items = {item.collection_id: item for item in inventory.items if item.state == "active"}
            with self.database.connect() as connection:
                needed = {UUID(row[0]): row[1] for row in connection.execute(
                    "SELECT c.collection_id, COUNT(*) FROM chunks c JOIN sources s "
                    "ON c.source_id = s.id AND c.generation = s.current_generation GROUP BY c.collection_id"
                )}
            if any(key not in active_items or active_items[key].vector_count < count for key, count in needed.items()):
                raise StorageError("当前资料缺少活动向量索引，未执行清理；请先修复或重建索引。")
            for item in active_items.values():
                self.catalog.verify_queryable(item.name, item.storage_id)
            logs = SQLiteOperationLogRepository(self.database)
            try:
                logs.record(OperationLog(action="index_cleanup_started", details={
                    "preview_id": preview_id, "targets": [item.name for item in candidates],
                }))
            except Exception:
                raise StorageError("无法记录清理操作，未删除任何索引。") from None
            deleted = []
            error = None
            for item in candidates:
                try:
                    active = self.profiles.get()
                    if active is None or active[1:] != (inventory.active_fingerprint, inventory.active_namespace):
                        raise ConflictError("活动索引已变化。")
                    if (item.collection_id is None
                            or item.name == ChromaVectorStore.collection_name(item.collection_id, active[2])
                            or self.collections.get(item.collection_id) is None):
                        raise ConflictError("目标不再满足清理条件。")
                    self.catalog.delete_checked(item.name, item.storage_id, str(item.collection_id), item.vector_count)
                    deleted.append(item.name)
                except Exception:
                    error = "清理未全部完成，后续目标已停止。请重新预览后重试。"
                    break
            remaining = tuple(item.name for item in candidates[len(deleted):])
            warning = None
            try:
                logs.record(OperationLog(action="index_cleanup_finished", details={
                    "preview_id": preview_id, "deleted": deleted, "remaining": list(remaining),
                    "complete": not remaining,
                }))
            except Exception:
                warning = "清理结果未能写入操作日志，请保留本次结果并重新预览核对。"
            return IndexCleanupResult(tuple(deleted), remaining, error, warning)

    def preview(self) -> IndexInventory:
        with self.catalog.session():
            return self._preview()

    def _preview(self) -> IndexInventory:
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
