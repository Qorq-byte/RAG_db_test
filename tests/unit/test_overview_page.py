import os
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog

from ragdb.config import AppSettings
from ragdb.desktop.pages import OverviewPage
from ragdb.desktop.window import MainWindow
from ragdb.domain.enums import ArtifactType, SourceType
from ragdb.domain.models import Collection, Conversation, IngestionTask, LearningArtifact, Source
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteSourceRepository
from ragdb.runtime import ApplicationRuntime


APP = QApplication.instance() or QApplication([])


@pytest.fixture
def runtime(tmp_path):
    database = SQLiteDatabase(tmp_path / "overview.sqlite3")
    database.initialize()
    app = ApplicationRuntime(AppSettings(), database)
    return app, app.collections.create(Collection(name="测试集合"))


def values(page):
    return tuple(card.value.text() for card in (
        page.source_count, page.session_count, page.artifact_count, page.task_count,
    ))


def add_records(app, collection):
    source = SQLiteSourceRepository(app.database).create(Source(collection_id=collection.id, source_type=SourceType.TEXT,
        title="资料", uri="manual://overview", content_hash="a" * 64))
    session = app.conversations.create(Conversation(collection_id=collection.id, provider="test", model="test"))
    artifact = app.artifacts.create(LearningArtifact(collection_id=collection.id,
        artifact_type=ArtifactType.OUTLINE, title="提纲", content="内容", provider="test", model="test"), [])
    app.tasks.create(IngestionTask(collection_id=collection.id))
    return source, session, artifact


def test_returning_to_overview_updates_added_and_deleted_records(runtime):
    app, collection = runtime
    window = MainWindow(app)
    window.show()
    try:
        window.collections_page.collections.setCurrentRow(0)
        assert values(window.overview_page) == ("0", "0", "0", "0")
        window.select_page(3)
        source, session, artifact = add_records(app, collection)
        window.select_page(0)
        assert values(window.overview_page) == ("1", "1", "1", "1")
        window.select_page(4)
        SQLiteSourceRepository(app.database).delete(source.id)
        app.conversations.delete_many(collection.id, [session.id])
        app.artifacts.delete(artifact.id)
        window.select_page(0)
        assert values(window.overview_page) == ("0", "0", "0", "1")
    finally:
        window.close()


def test_session_total_is_not_limited_to_recent_twenty(runtime):
    app, collection = runtime
    for _ in range(25):
        app.conversations.create(Conversation(collection_id=collection.id, provider="test", model="test"))
        app.tasks.create(IngestionTask(collection_id=collection.id))
    other = app.collections.create(Collection(name="另一集合"))
    app.conversations.create(Conversation(collection_id=other.id, provider="test", model="test"))
    page = OverviewPage(app)
    try:
        page.show_collection(collection.id, collection.name, 1)
        assert values(page) == ("0", "25", "0", "20")
        page.show_collection(other.id, other.name, 2)
        assert values(page) == ("0", "1", "0", "0")
    finally:
        page.close()


def test_visible_overview_polls_background_changes_and_stops_when_hidden(runtime):
    app, collection = runtime
    page = OverviewPage(app)
    page.show_collection(collection.id, collection.name, 1)
    page.show()
    try:
        add_records(app, collection)
        deadline = monotonic() + 5
        while values(page) != ("1", "1", "1", "1") and monotonic() < deadline:
            QTest.qWait(20)
        assert values(page) == ("1", "1", "1", "1")
        assert page.refresh_timer.isActive()
        page.hide()
        assert not page.refresh_timer.isActive()
    finally:
        page.close()


def test_no_selection_and_deleted_collection_clear_stale_counts(runtime):
    app, collection = runtime
    add_records(app, collection)
    page = OverviewPage(app)
    try:
        page.show_collection(collection.id, collection.name, 1)
        page.show_collection(None, "未选择集合", 2)
        assert values(page) == ("—",) * 4
        assert "请选择" in page.summary.text()
        page.show_collection(collection.id, collection.name, 3)
        app.collections.delete(collection.id)
        page.show()
        assert values(page) == ("—",) * 4
        assert "不存在" in page.summary.text()
    finally:
        page.close()


def test_failed_count_does_not_keep_stale_value_and_recovers(runtime, monkeypatch):
    app, collection = runtime
    add_records(app, collection)
    page = OverviewPage(app)
    page.show_collection(collection.id, collection.name, 1)
    try:
        with monkeypatch.context() as patch:
            def fail(*args, **kwargs):
                raise OSError("database unavailable")
            patch.setattr(type(app.conversations), "list_for_collection", fail)
            page.show_collection(collection.id, collection.name, 2)
            assert values(page) == ("1", "—", "1", "1")
            assert "失败" in page.guidance.text()
        page.show_collection(collection.id, collection.name, 3)
        assert values(page) == ("1", "1", "1", "1")
        assert "失败" not in page.guidance.text()
    finally:
        page.close()


def test_collection_read_failure_clears_all_counts_and_recovers(runtime, monkeypatch):
    app, collection = runtime
    add_records(app, collection)
    page = OverviewPage(app)
    page.show_collection(collection.id, collection.name, 1)
    try:
        with monkeypatch.context() as patch:
            def fail():
                raise OSError("database unavailable")
            patch.setattr(app, "collection_service", fail)
            page.refresh()
            assert values(page) == ("—",) * 4
            assert "失败" in page.summary.text()
        page.refresh()
        assert values(page) == ("1", "1", "1", "1")
    finally:
        page.close()


def test_background_desktop_import_updates_visible_overview(runtime, monkeypatch):
    app, collection = runtime
    monkeypatch.setattr(app, "_embedding_context", lambda: (app.settings.embedding, None, None))
    monkeypatch.setattr("ragdb.runtime.create_embedding_provider", lambda _: None)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *args: ("概览后台刷新测试资料", True))
    window = MainWindow(app)
    window.show()
    window.collections_page.collections.setCurrentRow(0)
    try:
        window.select_page(1)
        window.collections_page.import_text()
        window.select_page(0)
        deadline = monotonic() + 8
        while (window.collections_page._import_in_flight or values(window.overview_page) != ("1", "0", "0", "1")) and monotonic() < deadline:
            QTest.qWait(20)
        assert not window.collections_page._import_in_flight
        assert values(window.overview_page) == ("1", "0", "0", "1")
        assert "新增 1" in window.collections_page.feedback.text()
    finally:
        window.close()
