"""Versioned logical library archives with non-destructive restore."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

import tomlkit

from ragdb.config import AppSettings
from ragdb.domain.errors import ConflictError, StorageError
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteEmbeddingOperationGate
from ragdb.infrastructure.vectorstore.clients import open_client, close_client
from ragdb.infrastructure.vectorstore.query import read_collection


def _hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, default=lambda item: item.tolist()), encoding="utf-8")


class BackupService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.database = SQLiteDatabase(settings.storage.data_dir / settings.storage.sqlite_filename)
        self.chroma = settings.storage.data_dir / settings.storage.chroma_directory

    def create(self, destination: Path) -> dict:
        destination = destination.resolve()
        if destination.exists():
            raise ConflictError("备份文件已存在，请使用新文件名。")
        if not self.database.path.is_file():
            raise StorageError("知识库尚未创建。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ragdb-backup-", dir=destination.parent) as temporary:
            root = Path(temporary)
            collections = []
            with SQLiteEmbeddingOperationGate(self.database).rebuild():
                # Freeze all SQLite writes as well as gated vector mutations.
                with self.database.connect() as lock:
                    lock.execute("BEGIN IMMEDIATE")
                    with closing(sqlite3.connect(self.database.path)) as source, closing(sqlite3.connect(root / "library.sqlite3")) as target:
                        source.backup(target)
                    if (self.chroma / "chroma.sqlite3").exists():
                        client = open_client(self.chroma)
                        try:
                            for index, collection in enumerate(client.list_collections()):
                                count = collection.count()
                                filename = f"vectors-{index}.jsonl"
                                seen = set()
                                with (root / filename).open("w", encoding="utf-8") as output:
                                    for offset in range(0, count, 500):
                                        records = read_collection(collection, self.chroma, "get", {
                                            "limit": 500, "offset": offset,
                                            "include": ["embeddings", "documents", "metadatas"]})
                                        vectors = records.get("embeddings")
                                        if vectors is None:
                                            raise StorageError("索引缺少向量，备份中止。")
                                        for i, record_id in enumerate(records["ids"]):
                                            if record_id in seen:
                                                raise StorageError("备份期间索引记录不一致。")
                                            seen.add(record_id)
                                            row = dict(id=record_id, embedding=list(map(float, vectors[i])),
                                                       document=records["documents"][i], metadata=records["metadatas"][i])
                                            output.write(json.dumps(row, ensure_ascii=False) + "\n")
                                if len(seen) != count:
                                    raise StorageError("索引条数不一致，备份中止。")
                                collections.append(dict(name=collection.name, metadata=collection.metadata,
                                    hnsw=(collection.configuration.get("hnsw") or {}), count=count, file=filename))
                        finally:
                            close_client(client)
            values = self.settings.model_dump(mode="json", exclude={"embedding": {"cloud_api_key"}, "chat": {"cloud_api_key"}})
            values["storage"] = {"data_dir": ".", "sqlite_filename": "ragdb.sqlite3", "chroma_directory": "chroma"}
            _json(root / "settings.json", values)
            manifest = {"format": "ragdb-library", "version": 1, "collections": collections,
                        "files": {path.name: _hash(path) for path in root.iterdir()}}
            _json(root / "manifest.json", manifest)
            archive = root / "archive.zip"
            with ZipFile(archive, "w", ZIP_DEFLATED) as output:
                for name in [*manifest["files"], "manifest.json"]:
                    output.write(root / name, name)
            # Exclusive creation never overwrites an archive created concurrently.
            with destination.open("xb") as output, archive.open("rb") as source:
                shutil.copyfileobj(source, output)
        return {"path": str(destination), "collections": len(collections), "sha256": _hash(destination)}

    @staticmethod
    def _unpack(archive: Path, root: Path) -> dict:
        with ZipFile(archive) as source:
            names = source.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise StorageError("备份清单缺失或包含重复文件。")
            if source.getinfo("manifest.json").file_size > 10_000_000:
                raise StorageError("备份清单过大。")
            manifest = json.loads(source.read("manifest.json"))
            if manifest.get("format") != "ragdb-library" or manifest.get("version") != 1:
                raise StorageError("不支持的备份格式。")
            files = manifest["files"]
            if set(names) != set(files) | {"manifest.json"}:
                raise StorageError("备份文件清单不一致。")
            expected = {"library.sqlite3", "settings.json"} | {item["file"] for item in manifest["collections"]}
            if set(files) != expected:
                raise StorageError("备份内容不完整。")
            for name, checksum in files.items():
                if not name or Path(name).name != name or any(c in name for c in "/\\:") or name in {".", ".."}:
                    raise StorageError("备份含不安全的路径。")
                with source.open(name) as incoming, (root / name).open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                if _hash(root / name) != checksum:
                    raise StorageError("备份校验失败，文件已损坏。")
            with closing(sqlite3.connect(f"{(root / 'library.sqlite3').as_uri()}?mode=ro", uri=True)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StorageError("SQLite 完整性检查失败。")
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise StorageError("SQLite 关联数据检查失败。")
            AppSettings.model_validate(json.loads((root / "settings.json").read_text(encoding="utf-8")))
            return manifest

    @staticmethod
    def verify(archive: Path) -> dict:
        with tempfile.TemporaryDirectory(prefix="ragdb-verify-") as temporary:
            manifest = BackupService._unpack(archive, Path(temporary))
        return {"valid": True, "collections": len(manifest["collections"]), "sha256": _hash(archive)}

    @staticmethod
    def restore(archive: Path, destination: Path) -> Path:
        destination = destination.resolve()
        if destination.exists():
            raise ConflictError("恢复目录必须不存在；原知识库不会被覆盖。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ragdb-restore-", dir=destination.parent) as temporary:
            root = Path(temporary)
            unpacked = root / "archive"
            unpacked.mkdir()
            manifest = BackupService._unpack(archive, unpacked)
            restored = root / "restored"
            restored.mkdir()
            shutil.copyfile(unpacked / "library.sqlite3", restored / "ragdb.sqlite3")
            database = SQLiteDatabase(restored / "ragdb.sqlite3")
            database.initialize()
            with database.connect() as connection:
                connection.execute("UPDATE embedding_operation_gate SET rebuild_active = 0, rebuild_owner_pid = NULL")
                connection.execute("DELETE FROM embedding_ingestion_leases")
            client = open_client(restored / "chroma")
            try:
                for item in manifest["collections"]:
                    collection = client.create_collection(item["name"], metadata=item["metadata"],
                        configuration={"hnsw": item["hnsw"]}, embedding_function=None)
                    count = 0
                    with (unpacked / item["file"]).open(encoding="utf-8") as incoming:
                        for line in incoming:
                            row = json.loads(line)
                            args = {"ids": [row["id"]], "embeddings": [row["embedding"]]}
                            if row["document"] is not None:
                                args["documents"] = [row["document"]]
                            if row["metadata"]:
                                args["metadatas"] = [row["metadata"]]
                            collection.add(**args)
                            count += 1
                    if count != item["count"] or collection.count() != count:
                        raise StorageError("恢复向量条数不一致。")
            finally:
                close_client(client)
            values = json.loads((unpacked / "settings.json").read_text(encoding="utf-8"))
            values["storage"]["data_dir"] = str(destination)
            # TOML has no null; absent optional fields use application defaults.
            for section in values.values():
                if isinstance(section, dict):
                    for key in list(section):
                        if section[key] is None:
                            del section[key]
            (restored / "config.toml").write_text(tomlkit.dumps(values), encoding="utf-8")
            restored.rename(destination)
        return destination / "config.toml"
