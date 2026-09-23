import os
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QSettings, QThreadPool

from ragdb.desktop.window import MainWindow, PAGES
from ragdb.desktop.workers import BackgroundTask
from ragdb.domain.models import Collection
from ragdb.desktop.components import (
    DetailPanel,
    EmptyState,
    PageShell,
    ResultCard,
    StatCard,
    StatusBadge,
)
from ragdb.desktop.theme import ThemeManager, ThemeMode
from ragdb.desktop.study_pages import AsyncPage


APPLICATION = QApplication.instance() or QApplication([])


def test_main_window_exposes_all_workbench_pages() -> None:
    window = MainWindow()

    assert len(window.navigation.buttons) == len(PAGES)
    assert window.pages.count() == len(PAGES)
    window.navigation.select_page(3)
    assert window.pages.currentIndex() == 3
    window.close()
    APPLICATION.processEvents()


def test_sidebar_groups_and_collapsed_state() -> None:
    window = MainWindow()

    assert [label.text() for label in window.navigation.group_labels] == [
        "知识库",
        "学习",
        "系统",
    ]
    window.navigation.set_collapsed(True)

    assert window.navigation.collapsed is True
    assert all(
        button.text() == button.icon_text for button in window.navigation.buttons
    )
    assert window.navigation.collection.isHidden()
    window.close()


def test_narrow_window_collapses_navigation_and_details() -> None:
    window = MainWindow()
    window.show()
    window.resize(1024, 640)
    APPLICATION.processEvents()

    assert window.navigation.collapsed is True
    assert window.detail_panel.isHidden()
    window.close()


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

    def list_all(self):
        return self.items

    def create(self, name):
        self.items.append(Collection(name=name))

    def delete_by_name(self, name):
        self.items = [item for item in self.items if item.name != name]


class _Sources:
    def list_for_collection(self, collection):
        return []


class _EmptyStore:
    def list_for_collection(self, collection_id):
        return []

    def list_messages(self, session_id):
        return []

    def list_recent(self, collection_id):
        return []


class _Runtime:
    def __init__(self):
        self.collection_api = _Collections()
        self.conversations = _EmptyStore()
        self.artifacts = _EmptyStore()
        self.tasks = _EmptyStore()
        self.operation_logs = _EmptyStore()

    def collection_service(self):
        return self.collection_api

    def source_service(self):
        return _Sources()


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


def test_layout_preferences_are_normalized_and_persisted(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    settings.setValue("layout/sidebar_width", "not-a-number")
    manager = ThemeManager(settings)

    assert manager.sidebar_width() == 236
    manager.set_sidebar_width(999)
    manager.set_sidebar_collapsed(True)
    manager.set_detail_panel_visible(False)

    reloaded = ThemeManager(settings)
    assert reloaded.sidebar_width() == 400
    assert reloaded.sidebar_collapsed() is True
    assert reloaded.detail_panel_visible() is False


def test_responsive_layout_temporarily_overrides_saved_preferences(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    manager = ThemeManager(settings)
    manager.set_sidebar_width(280)
    manager.set_sidebar_collapsed(False)
    manager.set_detail_panel_visible(True)
    window = MainWindow(theme_manager=manager)
    window.show()
    window.select_page(2)
    APPLICATION.processEvents()

    assert window.navigation.collapsed is False
    assert window.detail_panel.isVisible()
    assert window.navigation.width() == 280

    window.resize(1024, 640)
    APPLICATION.processEvents()
    assert window.navigation.collapsed is True
    assert window.detail_panel.isHidden()
    assert manager.sidebar_collapsed() is False
    assert manager.detail_panel_visible() is True

    window.resize(1280, 800)
    APPLICATION.processEvents()
    assert window.navigation.collapsed is False
    assert window.detail_panel.isVisible()
    assert window.navigation.width() == 280
    window.close()


def test_detail_preference_is_restored_for_supported_pages(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    manager = ThemeManager(settings)
    window = MainWindow(theme_manager=manager)
    window.show()
    window.select_page(2)
    APPLICATION.processEvents()

    window.toggle_detail_preference()

    assert window.detail_panel.isHidden()
    assert manager.detail_panel_visible() is False
    window.close()


def test_async_page_prevents_duplicate_submission_and_restores_trigger() -> None:
    page = AsyncPage(None, "测试", "测试后台操作")
    trigger = QPushButton("执行")
    started, release = Event(), Event()
    completed = []

    def operation():
        started.set()
        release.wait(1)
        return "完成"

    assert page.run_task(operation, completed.append, trigger, "操作完成") is True
    assert started.wait(1)
    assert trigger.isEnabled() is False
    assert page.run_task(lambda: None, completed.append, trigger) is False
    assert "尚未完成" in page.feedback.text()

    release.set()
    QThreadPool.globalInstance().waitForDone(1000)
    APPLICATION.processEvents()

    assert trigger.isEnabled() is True
    assert completed == ["完成"]
    assert page.feedback.text() == "操作完成"


def test_async_page_recovers_trigger_after_failure() -> None:
    page = AsyncPage(None, "测试", "测试后台操作")
    trigger = QPushButton("执行")

    def operation():
        raise RuntimeError("连接失败")

    assert page.run_task(operation, lambda _result: None, trigger) is True
    QThreadPool.globalInstance().waitForDone(1000)
    APPLICATION.processEvents()

    assert trigger.isEnabled() is True
    assert page.feedback.text() == "失败：连接失败"


def test_shared_visual_components_construct_and_update() -> None:
    shell = PageShell("检索", "查找知识库证据")
    card = StatCard("资料", "12")
    badge = StatusBadge("通过", "success")
    empty = EmptyState("暂无结果", "尝试调整关键词")
    detail = DetailPanel()
    result = ResultCard("Python 指南", "一段可核验的证据", "#1 · guide.md")
    detail.show_text("来源内容", "来源")

    shell.set_content(card)
    assert shell.states.currentWidget() is card
    assert badge.property("status") == "success"
    assert empty is not None
    assert detail.title.text() == "来源"
    assert detail.content.toPlainText() == "来源内容"
    assert result.property("resultCard") is True


def test_runtime_pages_use_new_information_architecture() -> None:
    window = MainWindow(_Runtime())

    assert window.collections_page.sources.columnCount() == 3
    assert window.pages.widget(2).result_caption.text().startswith("结果")
    assert window.pages.widget(5).states.currentWidget().count() == 3
    window.close()
