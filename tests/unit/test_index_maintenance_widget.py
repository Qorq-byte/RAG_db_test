import os
import time
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication

from ragdb.application.index_maintenance import IndexInventory, IndexInventoryItem
from ragdb.desktop.index_maintenance_widget import IndexMaintenanceWidget


APPLICATION = QApplication.instance() or QApplication([])


def finish(widget):
    deadline = time.monotonic() + 10
    while widget.busy and time.monotonic() < deadline:
        APPLICATION.processEvents()
        time.sleep(0.005)
    assert not widget.busy


@pytest.fixture
def widget():
    service = SimpleNamespace(preview=lambda: IndexInventory("empty", "a" * 64, "legacy", ()))
    page = IndexMaintenanceWidget(SimpleNamespace(index_maintenance_service=lambda: service))
    page.show()
    yield page, service
    finish(page)
    page.close()


def test_preview_empty_and_background_duplicate_prevention(widget):
    page, service = widget
    assert page.inventory is None and not page.busy
    entered, release = Event(), Event()
    calls = []
    def preview():
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return IndexInventory("empty", "a" * 64, "legacy", ())
    service.preview = preview
    page.refresh_preview()
    try:
        assert entered.wait(5)
        page.refresh_preview()
        assert not page.refresh_button.isEnabled()
        assert len(calls) == 1
    finally:
        release.set()
    finish(page)
    assert page.refresh_button.isEnabled()
    assert "没有可清理" in page.feedback.text()


def test_preview_displays_safe_groups_and_clears_stale_result_on_failure(widget):
    page, service = widget
    service.preview = lambda: IndexInventory("token", "a" * 64, "a" * 64, (
        IndexInventoryItem("old-index", uuid4(), "中文资料", "legacy", 4, "stale", "可清理"),
        IndexInventoryItem("foreign", None, None, None, 0, "unknown", "需人工核查"),
    ))
    page.refresh_preview()
    finish(page)
    assert "中文资料" in page.view.toPlainText()
    assert "foreign" in page.view.toPlainText()
    assert "4 条向量" in page.view.toPlainText()
    def fail():
        raise RuntimeError("sensitive-internal-response")
    service.preview = fail
    page.refresh_preview()
    finish(page)
    assert page.inventory is None
    assert not page.view.toPlainText()
    assert "sensitive-internal-response" not in page.feedback.text()
    assert page.refresh_button.isEnabled()


def test_main_window_hosts_maintenance_without_collection_and_protects_busy_close(tmp_path):
    from ragdb.config import AppSettings, StorageSettings
    from ragdb.infrastructure.database import SQLiteDatabase
    from ragdb.runtime import ApplicationRuntime
    from ragdb.desktop.window import MainWindow

    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    runtime = ApplicationRuntime(AppSettings(storage=StorageSettings(data_dir=tmp_path)), database)
    window = MainWindow(runtime)
    window.show()
    page = window.operations_page.index_maintenance
    entered, release = Event(), Event()
    def work():
        entered.set()
        assert release.wait(5)
    page._run(work, lambda _: None)
    try:
        assert entered.wait(5)
        assert not window.close()
        assert window.isVisible()
    finally:
        release.set()
        finish(page)
        window.close()
