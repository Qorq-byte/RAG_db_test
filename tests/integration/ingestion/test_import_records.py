"""Import records must survive reopening the database, including failed attempts."""

from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from ragdb.config import AppSettings
from ragdb.domain.enums import TaskStatus
from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Collection
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteTaskRepository
from ragdb.runtime import ApplicationRuntime


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    database = SQLiteDatabase(tmp_path / "records.sqlite3")
    database.initialize()
    runtime = ApplicationRuntime(AppSettings(), database)
    # Exercise real parsing, SQL and runtime wiring without downloading a model.
    monkeypatch.setattr(runtime, "_embedding_context", lambda: (runtime.settings.embedding, None, None))
    monkeypatch.setattr("ragdb.runtime.create_embedding_provider", lambda _: None)
    collection = runtime.collections.create(Collection(name="任务记录测试"))
    return runtime, collection


@pytest.mark.parametrize("kind", ["file", "text", "web"])
def test_single_import_persists_task_and_logs(runtime, tmp_path, kind):
    app, collection = runtime
    service = app.ingestion_service()
    path = tmp_path / "note.txt"
    path.write_text("这是一段用于检查导入记录的资料。", encoding="utf-8")
    calls = {
        "file": lambda: service.ingest_file(collection, path),
        "text": lambda: service.ingest_text(collection, "这是一段手动输入的资料。"),
        "web": lambda: service.ingest_web_page(collection, "https://example.test", "网页", "网页中的资料正文。"),
    }
    calls[kind]()
    tasks = SQLiteTaskRepository(SQLiteDatabase(app.database.path)).list_for_collection(collection.id)
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.COMPLETED
    assert tasks[0].succeeded == 1
    assert tasks[0].finished_at is not None
    logs = app.operation_logs.list_recent(collection.id)
    assert {log.action for log in logs} == {"import_started", "import_finished"}
    assert all(log.details["task_id"] == str(tasks[0].id) for log in logs)


def test_failed_file_attempt_has_finished_record(runtime, tmp_path):
    app, collection = runtime
    with pytest.raises(DocumentParseError):
        app.ingestion_service().ingest_file(collection, tmp_path / "missing.txt")
    tasks = app.tasks.list_for_collection(collection.id)
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.FAILED
    assert tasks[0].failed == 1
    assert tasks[0].finished_at is not None
    assert app.operation_logs.list_recent(collection.id)[0].details["status"] == "failed"


def test_directory_records_one_task_and_live_counts(runtime, tmp_path):
    app, collection = runtime
    folder = tmp_path / "资料"
    folder.mkdir()
    (folder / "a.txt").write_text("资料一", encoding="utf-8")
    (folder / "b.txt").write_text("资料二", encoding="utf-8")
    snapshots = []
    result = app.ingestion_service().ingest_directory(
        collection, folder, on_item=lambda _: snapshots.append(app.tasks.list_for_collection(collection.id))
    )
    assert [len(snapshot) for snapshot in snapshots] == [1, 1]
    assert [snapshot[0].succeeded for snapshot in snapshots] == [1, 2]
    assert all(snapshot[0].status == TaskStatus.RUNNING for snapshot in snapshots)
    assert app.tasks.list_for_collection(collection.id) == [result.task]
    assert result.task.status == TaskStatus.COMPLETED
    assert result.task.succeeded == 2
    assert len(app.operation_logs.list_recent(collection.id)) == 2


def test_repeat_import_records_updated_and_skipped(runtime, tmp_path):
    app, collection = runtime
    path = tmp_path / "repeat.txt"
    path.write_text("第一版内容", encoding="utf-8")
    service = app.ingestion_service()
    service.ingest_file(collection, path)
    service.ingest_file(collection, path)
    path.write_text("第二版内容", encoding="utf-8")
    service.ingest_file(collection, path)
    tasks = app.tasks.list_for_collection(collection.id)
    assert [(task.succeeded, task.updated, task.skipped) for task in tasks] == [(0, 1, 0), (0, 0, 1), (1, 0, 0)]


def test_directory_partial_failure_and_desktop_wrapper_share_one_task(runtime, tmp_path):
    app, collection = runtime
    folder = tmp_path / "partial"
    folder.mkdir()
    (folder / "good.txt").write_text("可导入的内容", encoding="utf-8")
    (folder / "broken.pdf").write_bytes(b"not a PDF")
    result = app.run_import(collection, "directory", lambda: app.ingestion_service().ingest_directory(collection, folder))
    assert app.tasks.list_for_collection(collection.id) == [result.task]
    assert result.task.status == TaskStatus.PARTIAL
    assert (result.task.succeeded, result.task.failed) == (1, 1)
    assert len(app.operation_logs.list_recent(collection.id)) == 2


@pytest.mark.parametrize("kind", ["web", "repository", "initialization"])
def test_failure_before_parsing_is_recorded_without_sensitive_error(runtime, monkeypatch, kind):
    app, collection = runtime
    secret = "sk-private-do-not-log"
    def fail(*args):
        raise RuntimeError(f"remote failed: {secret}")
    if kind == "web":
        monkeypatch.setattr("ragdb.runtime.WebCrawler", lambda _: SimpleNamespace(crawl=fail, close=lambda: None))
        operation = lambda: app.ingest_web(collection, "https://example.test")
    elif kind == "repository":
        monkeypatch.setattr("ragdb.runtime.PublicGitHubImporter", lambda *args: SimpleNamespace(clone_and_list=fail))
        operation = lambda: app.ingest_repository(collection, "https://github.com/example/repo")
    else:
        monkeypatch.setattr(app, "ingestion_service", fail)
        operation = lambda: app.run_import(collection, "text", lambda: app.ingestion_service())
    with pytest.raises(RuntimeError, match=secret):
        operation()
    tasks = app.tasks.list_for_collection(collection.id)
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.FAILED
    assert tasks[0].failed == 1
    logs = app.operation_logs.list_recent(collection.id)
    assert len(logs) == 2
    assert secret not in repr(logs)
    assert logs[0].details["error_type"] == "RuntimeError"


@pytest.mark.parametrize("kind", ["web", "repository"])
def test_remote_batch_creates_one_task(runtime, tmp_path, monkeypatch, kind):
    app, collection = runtime
    if kind == "web":
        pages = [SimpleNamespace(url=f"https://example.test/{i}", title=f"页面 {i}", text=f"网页正文 {i}") for i in range(2)]
        monkeypatch.setattr("ragdb.runtime.WebCrawler", lambda _: SimpleNamespace(crawl=lambda _: pages, close=lambda: None))
        results = app.ingest_web(collection, "https://example.test")
    else:
        files = []
        for i in range(2):
            path = tmp_path / f"file{i}.txt"
            path.write_text(f"文件正文 {i}", encoding="utf-8")
            files.append(SimpleNamespace(path=path, repository_url="https://github.com/example/repo", relative_path=path.name))
        monkeypatch.setattr("ragdb.runtime.PublicGitHubImporter", lambda *args: SimpleNamespace(clone_and_list=lambda _: (tmp_path, files)))
        results = app.ingest_repository(collection, "https://github.com/example/repo")
    assert len(results) == 2
    tasks = app.tasks.list_for_collection(collection.id)
    assert len(tasks) == 1
    assert tasks[0].succeeded == 2
    assert tasks[0].status == TaskStatus.COMPLETED
    assert app.operation_logs.list_recent(collection.id)[0].details["kind"] == kind


def test_unexpected_batch_failure_finishes_task_and_next_import_is_independent(runtime, tmp_path):
    app, collection = runtime
    folder = tmp_path / "unexpected"
    folder.mkdir()
    (folder / "good.txt").write_text("已入库资料", encoding="utf-8")
    def failed_callback(_):
        raise RuntimeError("callback failed")
    with pytest.raises(RuntimeError, match="callback failed"):
        app.ingestion_service().ingest_directory(collection, folder, on_item=failed_callback)
    first = app.tasks.list_for_collection(collection.id)[0]
    assert first.status == TaskStatus.PARTIAL
    assert first.finished_at is not None
    app.ingestion_service().ingest_text(collection, "另一次独立导入")
    tasks = app.tasks.list_for_collection(collection.id)
    assert len(tasks) == 2
    assert tasks[0].status == TaskStatus.COMPLETED
    assert tasks[0].succeeded == 1


def test_concurrent_imports_do_not_share_task(runtime):
    app, collection = runtime
    barrier = Barrier(2)
    def execute(index):
        def operation():
            barrier.wait(timeout=10)
            return app.ingestion_service().ingest_text(collection, f"并发资料 {index}")
        return app.run_import(collection, "text", operation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(execute, range(2)))
    tasks = app.tasks.list_for_collection(collection.id)
    assert len(tasks) == 2
    assert all(task.status == TaskStatus.COMPLETED and task.succeeded == 1 for task in tasks)
