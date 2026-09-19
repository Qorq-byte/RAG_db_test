from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from ragdb.application.ingestion import LocalIngestionService
from ragdb.cli import app
from ragdb.config import ChunkingSettings
from ragdb.domain.enums import SourceStatus, TaskItemStatus, TaskStatus
from ragdb.domain.errors import OcrRequiredError
from ragdb.domain.models import Collection
from ragdb.infrastructure.chunking import StructuredChunker
from ragdb.infrastructure.database import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteDatabase,
    SQLiteKeywordIndex,
    SQLiteSourceRepository,
    SQLiteTaskRepository,
)
from ragdb.infrastructure.parsers import ParserRegistry


@pytest.fixture
def ingestion(tmp_path: Path):
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    collections = SQLiteCollectionRepository(database)
    collection = collections.create(Collection(name="学习资料"))
    sources = SQLiteSourceRepository(database)
    chunks = SQLiteChunkRepository(database)
    keyword = SQLiteKeywordIndex(database)
    service = LocalIngestionService(
        sources,
        chunks,
        SQLiteTaskRepository(database),
        ParserRegistry(),
        StructuredChunker(ChunkingSettings(max_characters=200, overlap_characters=20)),
        keyword,
        max_file_size_bytes=1000,
    )
    return service, collection, sources, chunks, keyword


def test_file_ingestion_supports_unicode_path_skip_and_update(tmp_path, ingestion) -> None:
    service, collection, sources, chunks, keyword = ingestion
    directory = tmp_path / "中文目录"
    directory.mkdir()
    path = directory / "人工智能笔记.md"
    path.write_text("# 第一版\n\n旧内容", encoding="utf-8")

    created = service.ingest_file(collection, path)
    repeated = service.ingest_file(collection, path)
    path.write_text("# 第二版\n\n全新的检索内容", encoding="utf-8")
    updated = service.ingest_file(collection, path)

    assert created.status is TaskItemStatus.CREATED
    assert repeated.status is TaskItemStatus.SKIPPED
    assert updated.status is TaskItemStatus.UPDATED
    assert updated.source is not None
    assert updated.source.status is SourceStatus.READY
    assert updated.source.current_generation == 2
    stored = sources.get_by_uri(collection.id, path.resolve().as_uri())
    assert stored == updated.source
    stored_chunks = chunks.list_for_source(updated.source.id)
    assert {chunk.generation for chunk in stored_chunks} == {2}
    assert keyword.search(collection.id, "全新的检索内容", 5)
    assert keyword.search(collection.id, "旧内容", 5) == []


def test_directory_ingestion_filters_directories_extensions_and_size(tmp_path, ingestion) -> None:
    service, collection, _, _, _ = ingestion
    root = tmp_path / "资料集"
    root.mkdir()
    (root / "notes.txt").write_text("有效文本", encoding="utf-8")
    (root / "module.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    (root / "image.bin").write_bytes(b"ignored")
    (root / "large.txt").write_text("x" * 1001, encoding="utf-8")
    hidden = root / ".hidden"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("不应导入", encoding="utf-8")
    dependency = root / "node_modules"
    dependency.mkdir()
    (dependency / "package.js").write_text("ignored()", encoding="utf-8")

    result = service.ingest_directory(collection, root)

    assert result.task.status is TaskStatus.COMPLETED
    assert result.task.succeeded == 2
    assert result.task.skipped == 1
    assert result.task.failed == 0
    assert len(result.items) == 3
    assert {Path(item.uri).name for item in result.items if item.source} == {
        "notes.txt",
        "module.py",
    }


def test_manual_text_is_stable_and_not_duplicated(ingestion) -> None:
    service, collection, sources, chunks, _ = ingestion
    first = service.ingest_text(collection, "手动输入的知识", "随手记")
    repeated = service.ingest_text(collection, "  手动输入的知识  ", "另一个标题")

    assert first.status is TaskItemStatus.CREATED
    assert repeated.status is TaskItemStatus.SKIPPED
    assert first.source is not None
    assert sources.list_for_collection(collection.id) == [first.source]
    assert len(chunks.list_for_source(first.source.id)) == 1


def test_scanned_pdf_is_recorded_as_ocr_required(tmp_path, ingestion) -> None:
    service, collection, sources, _, _ = ingestion
    path = tmp_path / "扫描件.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(path)

    with pytest.raises(OcrRequiredError):
        service.ingest_file(collection, path)

    source = sources.get_by_uri(collection.id, path.resolve().as_uri())
    assert source is not None
    assert source.status is SourceStatus.OCR_REQUIRED
    assert source.current_generation == 0
    assert "OCR" in (source.error_message or "")


def test_cli_ingests_and_lists_source(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    config = tmp_path / "config.toml"
    config.write_text(f'[storage]\ndata_dir = "{data_dir.as_posix()}"\n', encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["--config", str(config), "collection", "create", "CLI 集合"]).exit_code == 0

    imported = runner.invoke(
        app,
        ["--config", str(config), "ingest", "text", "CLI 文本", "-c", "CLI 集合", "--title", "命令行资料"],
    )
    listed = runner.invoke(
        app, ["--config", str(config), "source", "list", "-c", "CLI 集合"]
    )

    assert imported.exit_code == 0
    assert "已导入" in imported.stdout
    assert listed.exit_code == 0
    assert "命令行资料" in listed.stdout
    assert "ready" in listed.stdout
