import os
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog

from ragdb.application.ingestion import DirectoryIngestionResult, IngestionResult
from ragdb.config import AppSettings
from ragdb.desktop.import_feedback import import_feedback
from ragdb.desktop.operations_page import OperationsPage
from ragdb.desktop.window import MainWindow
from ragdb.domain.enums import TaskItemStatus, TaskStatus
from ragdb.domain.models import Collection, IngestionTask, OperationLog, utc_now
from ragdb.infrastructure.database import SQLiteDatabase
from ragdb.runtime import ApplicationRuntime


APPLICATION = QApplication.instance() or QApplication([])


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    database = SQLiteDatabase(tmp_path / "desktop.sqlite3")
    database.initialize()
    app = ApplicationRuntime(AppSettings(), database)
    monkeypatch.setattr(app, "_embedding_context", lambda: (app.settings.embedding, None, None))
    monkeypatch.setattr("ragdb.runtime.create_embedding_provider", lambda _: None)
    collection = app.collections.create(Collection(name="页面测试"))
    return app, collection


def wait_until(predicate, timeout=10000):
    deadline = monotonic() + timeout / 1000
    while not predicate() and monotonic() < deadline:
        QTest.qWait(20)
    assert predicate()


def test_desktop_text_import_populates_both_pages_immediately(runtime, monkeypatch):
    app, collection = runtime
    window = MainWindow(app)
    window.collections_page.collections.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *args: ("真实桌面导入流程中的测试资料", True))
    try:
        window.collections_page.import_text()
        wait_until(lambda: not window.collections_page._import_in_flight)
        assert "新增 1" in window.operations_page.tasks_view.toPlainText()
        assert "已完成" in window.operations_page.tasks_view.toPlainText()
        assert "文本导入 · 已完成" in window.operations_page.logs_view.toPlainText()
        assert "新增 1" in window.collections_page.feedback.text()
        assert len(app.tasks.list_for_collection(collection.id)) == 1
        window.collections_page.import_text()
        wait_until(lambda: not window.collections_page._import_in_flight)
        assert "已跳过" in window.collections_page.feedback.text()
        assert "跳过 1" in window.operations_page.tasks_view.toPlainText()
    finally:
        window.close()


def test_desktop_initialization_failure_refreshes_records_and_reenables_import(runtime, monkeypatch):
    app, collection = runtime
    window = MainWindow(app)
    window.collections_page.collections.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *args: ("资料", True))
    def fail():
        raise RuntimeError("模型不可用")
    monkeypatch.setattr(app, "ingestion_service", fail)
    try:
        window.collections_page.import_text()
        wait_until(lambda: not window.collections_page._import_in_flight)
        assert window.collections_page.import_button.isEnabled()
        assert "导入失败" in window.collections_page.feedback.text()
        assert "失败 1" in window.operations_page.tasks_view.toPlainText()
        assert "文本导入 · 失败" in window.operations_page.logs_view.toPlainText()
        assert app.tasks.list_for_collection(collection.id)[0].finished_at is not None
    finally:
        window.close()


def test_visible_page_refreshes_progress_and_hidden_page_stops_polling(runtime):
    app, collection = runtime
    page = OperationsPage(app)
    page.set_collection(collection.id, collection.name, 1)
    task = app.tasks.create(IngestionTask(collection_id=collection.id, status=TaskStatus.RUNNING))
    page.refresh_timer.setInterval(20)
    page.show()
    try:
        assert "处理中" in page.tasks_view.toPlainText()
        assert page.refresh_timer.isActive()
        app.tasks.update(task.model_copy(update={
            "status": TaskStatus.COMPLETED, "updated": 2, "skipped": 3, "finished_at": utc_now(),
        }))
        wait_until(lambda: "更新 2 / 跳过 3" in page.tasks_view.toPlainText())
        assert "已完成" in page.tasks_view.toPlainText()
        page.hide()
        assert not page.refresh_timer.isActive()
        app.operation_logs.record(OperationLog(collection_id=collection.id, action="source_ingested"))
        page.show()
        assert "资料已导入" in page.logs_view.toPlainText()
    finally:
        page.close()


def test_switching_collection_does_not_show_previous_records(runtime):
    app, collection = runtime
    other = app.collections.create(Collection(name="另一个集合"))
    app.ingestion_service().ingest_text(collection, "集合一的资料")
    page = OperationsPage(app)
    try:
        page.set_collection(collection.id, collection.name, 1)
        assert "新增 1" in page.tasks_view.toPlainText()
        page.set_collection(other.id, other.name, 2)
        assert "暂无任务" in page.tasks_view.toPlainText()
        assert "暂无操作日志" in page.logs_view.toPlainText()
        page.set_collection(None, "", 3)
        assert "请选择知识集合" in page.tasks_view.toPlainText()
        assert "请选择知识集合" in page.logs_view.toPlainText()
    finally:
        page.close()


def test_record_read_failure_is_visible_and_can_recover(runtime, monkeypatch):
    app, collection = runtime
    page = OperationsPage(app)
    page.set_collection(collection.id, collection.name, 1)
    from ragdb.infrastructure.database import SQLiteTaskRepository
    def fail(*args):
        raise OSError("private path")
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteTaskRepository, "list_for_collection", fail)
        page.refresh()
        assert "读取任务记录失败" in page.tasks_view.toPlainText()
        assert "private path" not in page.tasks_view.toPlainText()
    page.refresh()
    assert "暂无任务" in page.tasks_view.toPlainText()
    page.close()


@pytest.mark.parametrize(("statuses", "text", "severity"), [
    ([TaskItemStatus.CREATED], "导入完成", "success"),
    ([TaskItemStatus.UPDATED], "更新 1", "success"),
    ([TaskItemStatus.SKIPPED], "已跳过", "warning"),
    ([TaskItemStatus.FAILED], "导入失败", "failure"),
    ([TaskItemStatus.CREATED, TaskItemStatus.FAILED], "部分导入失败", "warning"),
    ([], "未发现可导入资料", "warning"),
])
def test_import_feedback_reflects_actual_outcome(statuses, text, severity):
    items = [IngestionResult("manual://test", status) for status in statuses]
    result = DirectoryIngestionResult(IngestionTask(collection_id=Collection(name="测试").id), tuple(items))
    message, actual_severity = import_feedback(result)
    assert text in message
    assert actual_severity == severity
