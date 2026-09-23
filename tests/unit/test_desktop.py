import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from ragdb.desktop.window import MainWindow, PAGES
from ragdb.desktop.workers import BackgroundTask
from ragdb.domain.models import Collection
from ragdb.desktop.components import DetailPanel, EmptyState, PageShell, StatCard, StatusBadge
from ragdb.desktop.theme import ThemeManager, ThemeMode


APPLICATION = QApplication.instance() or QApplication([])


def test_main_window_exposes_all_workbench_pages() -> None:
    window = MainWindow()

    assert window.navigation.count() == len(PAGES)
    assert window.pages.count() == len(PAGES)
    window.navigation.setCurrentRow(3)
    assert window.pages.currentIndex() == 3
    window.close()
    APPLICATION.processEvents()


def test_collection_context_invalidates_previous_generation() -> None:
    window = MainWindow()
    window.collection_context.select("one", "集合一")
    first = window.collection_context.generation
    window.collection_context.select("two", "集合二")

    assert window.collection_context.generation == first + 1
    assert window.collection_context.collection_name == "集合二"
    window.close()
    APPLICATION.processEvents()


def test_background_task_emits_result_and_context_token() -> None:
    seen = []
    task = BackgroundTask("collection-2", lambda: 42)
    task.signals.succeeded.connect(lambda token, result: seen.append((token, result)))

    task.run()
    APPLICATION.processEvents()

    assert seen == [("collection-2", 42)]


class _Collections:
    def __init__(self):
        self.items = [Collection(name="人工智能")]

    def list_all(self): return self.items
    def create(self, name): self.items.append(Collection(name=name))
    def delete_by_name(self, name): self.items = [item for item in self.items if item.name != name]


class _Sources:
    def list_for_collection(self, collection): return []


class _EmptyStore:
    def list_for_collection(self, collection_id): return []
    def list_messages(self, session_id): return []
    def list_recent(self, collection_id): return []


class _Runtime:
    def __init__(self):
        self.collection_api = _Collections()
        self.conversations = _EmptyStore()
        self.artifacts = _EmptyStore()
        self.tasks = _EmptyStore()
        self.operation_logs = _EmptyStore()
    def collection_service(self): return self.collection_api
    def source_service(self): return _Sources()


def test_collection_selection_updates_global_context_and_overview() -> None:
    window = MainWindow(_Runtime())

    window.collections_page.collections.setCurrentRow(0)
    APPLICATION.processEvents()

    assert window.collection_context.collection_name == "人工智能"
    assert "人工智能" in window.overview_page.summary.text()
    window.close()


def test_theme_preferences_are_persisted_and_applied(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    manager = ThemeManager(settings)

    manager.set_mode(ThemeMode.DARK)
    manager.set_reduce_motion(True)

    reloaded = ThemeManager(settings)
    assert reloaded.mode is ThemeMode.DARK
    assert reloaded.reduce_motion is True
    assert "#101419" in APPLICATION.styleSheet()


def test_shared_visual_components_construct_and_update() -> None:
    shell = PageShell("检索", "查找知识库证据")
    card = StatCard("资料", "12")
    badge = StatusBadge("通过", "success")
    empty = EmptyState("暂无结果", "尝试调整关键词")
    detail = DetailPanel()
    detail.show_text("来源内容", "来源")

    shell.set_content(card)
    assert shell.states.currentWidget() is card
    assert badge.property("status") == "success"
    assert empty is not None
    assert detail.title.text() == "来源"
    assert detail.content.toPlainText() == "来源内容"
