"""Local file, directory, and manual-text ingestion orchestration."""

import hashlib
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ragdb.domain.enums import SourceStatus, SourceType, TaskItemStatus, TaskStatus
from ragdb.domain.errors import DocumentParseError, OcrRequiredError, RagdbError, UnsupportedSourceError
from ragdb.domain.models import Collection, Document, DocumentUnit, IngestionTask, Source, utc_now
from ragdb.domain.models import Metadata
from ragdb.domain.ports import (
    ChunkRepository,
    Chunker,
    EmbeddingProvider,
    KeywordIndex,
    SourceRepository,
    TaskRepository,
    VectorStore,
)
from ragdb.infrastructure.parsers.registry import ParserRegistry


SOURCE_TYPES_BY_EXTENSION = {
    ".pdf": SourceType.PDF,
    ".md": SourceType.MARKDOWN,
    ".markdown": SourceType.MARKDOWN,
    ".txt": SourceType.TEXT,
    ".text": SourceType.TEXT,
    ".docx": SourceType.WORD,
    ".pptx": SourceType.POWERPOINT,
}

CODE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".kt", ".php", ".py", ".rb", ".rs", ".sh",
    ".sql", ".swift", ".ts", ".tsx", ".vue", ".xml", ".yaml", ".yml",
}

IGNORED_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules",
    "vendor", "dist", "build", "target",
}


@dataclass(frozen=True, slots=True)
class IngestionResult:
    uri: str
    status: TaskItemStatus
    source: Source | None = None
    message: str | None = None
    chunk_count: int = 0


@dataclass(frozen=True, slots=True)
class DirectoryIngestionResult:
    task: IngestionTask
    items: tuple[IngestionResult, ...]


class LocalIngestionService:
    def __init__(
        self,
        source_repository: SourceRepository,
        chunk_repository: ChunkRepository,
        task_repository: TaskRepository,
        parser_registry: ParserRegistry,
        chunker: Chunker,
        keyword_index: KeywordIndex,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        generation_repository: object | None = None,
        max_file_size_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        if max_file_size_bytes < 1:
            raise ValueError("max_file_size_bytes must be positive")
        self.source_repository = source_repository
        self.chunk_repository = chunk_repository
        self.task_repository = task_repository
        self.parser_registry = parser_registry
        self.chunker = chunker
        self.keyword_index = keyword_index
        if (embedding_provider is None) != (vector_store is None):
            raise ValueError("嵌入模型与向量库必须同时配置")
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.generation_repository = generation_repository
        self.max_file_size_bytes = max_file_size_bytes

    def ingest_file(self, collection: Collection, path: Path, metadata: Mapping[str, object] | None = None) -> IngestionResult:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise DocumentParseError(str(path), "文件不存在或不是普通文件")
        source_type = source_type_for_path(resolved)
        if source_type is None:
            raise UnsupportedSourceError(resolved.suffix.lower() or "unknown", str(resolved))
        if resolved.stat().st_size > self.max_file_size_bytes:
            return IngestionResult(
                uri=resolved.as_uri(),
                status=TaskItemStatus.SKIPPED,
                message=f"文件超过大小限制（{self.max_file_size_bytes} 字节）",
            )

        content_hash = hash_file(resolved)
        uri = resolved.as_uri()
        existing = self.source_repository.get_by_uri(collection.id, uri)
        source_metadata = {"filename": resolved.name, "size_bytes": resolved.stat().st_size, **(metadata or {})}
        if existing is not None and existing.content_hash == content_hash and existing.metadata == source_metadata:
            return IngestionResult(uri, TaskItemStatus.SKIPPED, existing, "内容未变化")
        self._cleanup_stale_vectors(existing)

        source = self._prepare_source(
            collection=collection,
            existing=existing,
            source_type=source_type,
            title=resolved.stem,
            uri=uri,
            content_hash=content_hash,
            metadata=source_metadata,
        )
        parser = self.parser_registry.get_parser(source)
        source = source.model_copy(update={"parser_name": parser.name, "parser_version": parser.version})
        self.source_repository.update(source)
        return self._parse_and_store(source, existing, lambda: parser.parse(source))

    def _cleanup_stale_vectors(self, source: Source | None) -> None:
        if source is None or source.current_generation == 0 or self.vector_store is None:
            return
        cleanup = getattr(self.vector_store, "delete_stale_source_generations", None)
        if cleanup is not None:
            cleanup(source.collection_id, source.id, source.current_generation)

    def ingest_text(
        self,
        collection: Collection,
        text: str,
        title: str = "手动文本", metadata: Mapping[str, object] | None = None,
    ) -> IngestionResult:
        normalized = text.strip()
        if not normalized:
            raise DocumentParseError("manual://text", "文本不能为空")
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        uri = f"manual://{content_hash}"
        existing = self.source_repository.get_by_uri(collection.id, uri)
        source_metadata = {"character_count": len(normalized), **(metadata or {})}
        if existing is not None and existing.metadata == source_metadata:
            return IngestionResult(uri, TaskItemStatus.SKIPPED, existing, "内容未变化")

        source = self._prepare_source(
            collection=collection,
            existing=None,
            source_type=SourceType.MANUAL_TEXT,
            title=title,
            uri=uri,
            content_hash=content_hash,
            metadata=source_metadata,
        ).model_copy(update={"parser_name": "manual_text", "parser_version": "1.0"})
        self.source_repository.update(source)
        return self._parse_and_store(
            source,
            None,
            lambda: Document(
                source_id=source.id,
                title=source.title,
                units=(DocumentUnit(text=normalized),),
                metadata={"format": "manual_text"},
            ),
        )

    def ingest_web_page(self, collection: Collection, url: str, title: str, text: str, metadata: Mapping[str, object] | None = None) -> IngestionResult:
        normalized = text.strip()
        if not normalized:
            raise DocumentParseError(url, "网页不包含可索引正文")
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        existing = self.source_repository.get_by_uri(collection.id, url)
        source_metadata = {"url": url, **(metadata or {})}
        if existing is not None and existing.content_hash == content_hash and existing.metadata == source_metadata:
            return IngestionResult(url, TaskItemStatus.SKIPPED, existing, "内容未变化")
        self._cleanup_stale_vectors(existing)
        source = self._prepare_source(
            collection=collection, existing=existing, source_type=SourceType.WEB,
            title=title, uri=url, content_hash=content_hash, metadata=source_metadata,
        ).model_copy(update={"parser_name": "web", "parser_version": "1.0"})
        self.source_repository.update(source)
        return self._parse_and_store(
            source, existing,
            lambda: Document(source_id=source.id, title=source.title, units=(DocumentUnit(text=normalized),), metadata={"format": "web", "url": url}),
        )

    def ingest_directory(
        self, collection: Collection, path: Path, metadata: Mapping[str, object] | None = None,
        on_item: Callable[[IngestionResult], None] | None = None,
    ) -> DirectoryIngestionResult:
        resolved = path.expanduser().resolve()
        if not resolved.is_dir():
            raise DocumentParseError(str(path), "目录不存在")
        task = self.task_repository.create(
            IngestionTask(collection_id=collection.id, status=TaskStatus.RUNNING)
        )
        items: list[IngestionResult] = []
        for file_path in iter_supported_files(resolved):
            try:
                item = self.ingest_file(collection, file_path, metadata)
            except RagdbError as exc:
                item = IngestionResult(
                    uri=file_path.resolve().as_uri(), status=TaskItemStatus.FAILED,
                    message=str(exc),
                )
            items.append(item)
            if on_item is not None:
                on_item(item)

        created = sum(item.status is TaskItemStatus.CREATED for item in items)
        updated = sum(item.status is TaskItemStatus.UPDATED for item in items)
        skipped = sum(item.status is TaskItemStatus.SKIPPED for item in items)
        failed = sum(item.status is TaskItemStatus.FAILED for item in items)
        successful = created + updated + skipped
        status = TaskStatus.COMPLETED
        if failed and successful:
            status = TaskStatus.PARTIAL
        elif failed:
            status = TaskStatus.FAILED
        finished = task.model_copy(
            update={
                "status": status,
                "finished_at": utc_now(),
                "succeeded": created,
                "updated": updated,
                "skipped": skipped,
                "failed": failed,
            }
        )
        self.task_repository.update(finished)
        return DirectoryIngestionResult(finished, tuple(items))

    def _prepare_source(
        self,
        *,
        collection: Collection,
        existing: Source | None,
        source_type: SourceType,
        title: str,
        uri: str,
        content_hash: str,
        metadata: Metadata,
    ) -> Source:
        if existing is None:
            source = Source(
                collection_id=collection.id,
                source_type=source_type,
                title=title,
                uri=uri,
                content_hash=content_hash,
                status=SourceStatus.PROCESSING,
                metadata=metadata,
            )
            return self.source_repository.create(source)
        source = existing.model_copy(
            update={
                "source_type": source_type,
                "title": title,
                "content_hash": content_hash,
                "status": SourceStatus.PROCESSING,
                "metadata": metadata,
                "updated_at": utc_now(),
                "error_message": None,
            }
        )
        return self.source_repository.update(source)

    def _parse_and_store(
        self,
        source: Source,
        previous: Source | None,
        parse: Callable[[], Document],
    ) -> IngestionResult:
        generation = source.current_generation + 1
        stored_chunks = False
        stored_vectors = False
        try:
            document = parse()
            chunks = tuple(
                chunk.model_copy(update={"metadata": {**source.metadata, **chunk.metadata, "source_type": source.source_type.value}})
                for chunk in self.chunker.chunk(
                    document,
                    source.collection_id,
                    source.content_hash,
                    generation,
                )
            )
            if self.embedding_provider is not None and self.vector_store is not None:
                embeddings = self.embedding_provider.embed_texts([chunk.text for chunk in chunks])
                if len(embeddings) != len(chunks):
                    raise RuntimeError("嵌入模型返回的向量数量与切片数量不一致")
                # New vectors are written before SQLite points the source at them.
                self.vector_store.upsert(chunks, embeddings)
                stored_vectors = True
            updates = {
                "status": SourceStatus.READY,
                "current_generation": generation,
                "updated_at": utc_now(),
                "error_message": None,
            }
            if self.embedding_provider is not None:
                updates["embedding_provider"] = self.embedding_provider.provider_name
                updates["embedding_model"] = self.embedding_provider.model_name
            ready = source.model_copy(
                update=updates
            )
            if self.generation_repository is not None:
                self.generation_repository.activate(ready, chunks)
            else:
                self.chunk_repository.add_many(chunks)
                self.source_repository.update(ready)
            stored_chunks = True
            self.keyword_index.index(chunks)
            if previous is not None and previous.current_generation > 0:
                self.chunk_repository.delete_source_generation(
                    source.id, previous.current_generation
                )
                if self.vector_store is not None:
                    self.vector_store.delete_source_generation(
                        source.collection_id, source.id, previous.current_generation
                    )
            status = TaskItemStatus.CREATED if previous is None else TaskItemStatus.UPDATED
            return IngestionResult(source.uri, status, ready, chunk_count=len(chunks))
        except Exception as exc:
            if stored_chunks:
                self.chunk_repository.delete_source_generation(source.id, generation)
            if stored_vectors and self.vector_store is not None:
                self.vector_store.delete_source_generation(
                    source.collection_id, source.id, generation
                )
            failure_status = SourceStatus.OCR_REQUIRED if isinstance(exc, OcrRequiredError) else SourceStatus.FAILED
            # An update which fails to embed must leave its previously usable
            # generation discoverable; only a first import becomes failed.
            failed_base = previous or source
            failed = failed_base.model_copy(
                update={
                    "status": SourceStatus.READY if previous and previous.current_generation else failure_status,
                    "updated_at": utc_now(),
                    "error_message": str(exc),
                }
            )
            self.source_repository.update(failed)
            if isinstance(exc, RagdbError):
                raise
            raise DocumentParseError(source.uri, str(exc)) from exc


def source_type_for_path(path: Path) -> SourceType | None:
    extension = path.suffix.lower()
    if extension in CODE_EXTENSIONS:
        return SourceType.CODE
    return SOURCE_TYPES_BY_EXTENSION.get(extension)


def hash_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def iter_supported_files(root: Path) -> Sequence[Path]:
    files: list[Path] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES and not directory.startswith(".")
        )
        current_path = Path(current)
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            path = current_path / filename
            if source_type_for_path(path) is not None:
                files.append(path)
    return tuple(files)
