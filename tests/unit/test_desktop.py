import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QInputDialog, QPushButton
from PySide6.QtCore import QSettings, QThreadPool, Qt

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
from ragdb.config import AppSettings


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
        self.settings = AppSettings()
        self.config_path = Path("__missing_test_config__.toml")
        self.collection_api = _Collections()
        self.collections = self.collection_api
        self.conversations = _EmptyStore()
        self.artifacts = _EmptyStore()
        self.tasks = _EmptyStore()
        self.operation_logs = _EmptyStore()

    def collection_service(self):
        return self.collection_api

    def source_service(self):
        return _Sources()

    def active_embedding_settings(self):
        return self.settings.embedding


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


def test_navigation_resize_handle_is_keyboard_accessible(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    manager = ThemeManager(settings)
    window = MainWindow(theme_manager=manager)

    handle = window.navigation.resize_handle
    assert handle.accessibleName() == "调整导航栏宽度"
    assert handle.focusPolicy().name == "StrongFocus"
    handle.width_adjusted_by_key.emit(8)

    assert window.navigation.width() == 244
    assert manager.sidebar_width() == 244
    window.close()


def test_window_shortcuts_and_escape_follow_interaction_priority(tmp_path) -> None:
    settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    window = MainWindow(theme_manager=ThemeManager(settings))
    window.show()
    window._select_page_from_shortcut(3)
    APPLICATION.processEvents()

    assert window.pages.currentIndex() == 3
    window._toggle_sidebar_from_shortcut()
    assert window.navigation.collapsed is True

    window.navigation.set_collapsed(False)
    window.select_page(2)
    assert window.detail_panel.isVisible()
    assert window.handle_escape() is True
    assert window.detail_panel.isHidden()
    assert ThemeManager(settings).detail_panel_visible() is False
    window.close()


def test_window_shortcuts_do_not_override_multiline_editor_focus() -> None:
    window = MainWindow(_Runtime())
    window.show()
    window.select_page(3)
    window.pages.widget(3).transcript.setFocus()
    APPLICATION.processEvents()

    window._select_page_from_shortcut(1)

    assert window.pages.currentIndex() == 3
    window.close()


def test_chat_collection_switch_syncs_workbench_and_actual_request(monkeypatch):
    from types import SimpleNamespace
    runtime = _Runtime()
    second = Collection(name="计算机网络")
    runtime.collection_api.items.append(second)
    window = MainWindow(runtime)
    window.collections_page.collections.setCurrentRow(0)
    window.navigation.select_page(3)
    page = window.chat_page
    page._add_bubble("assistant", "上一个集合的回答")
    page.question.setPlainText("尚未发送的问题")
    window.detail_panel.show_text("上一个集合的引用")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (second.name, True))
    page.switch_collection.click()
    assert window.pages.currentIndex() == 3
    assert page.collection_label.text() == "当前提问集合：计算机网络"
    assert page.collection_id == window.collection_context.collection_id == second.id
    assert window.top_bar.collection.text() == window.navigation.collection.text() == second.name
    assert window.collections_page.collections.currentItem().data(Qt.ItemDataRole.UserRole).id == second.id
    assert window.pages.widget(2).collection_id == window.operations_page.collection_id == second.id
    assert page.transcript.messages[0].content == "上一个集合的回答"
    assert page.session_id is None  # Unsaved conversations also keep their visible messages.
    assert window.details.toPlainText() == "上一个集合的引用"
    assert page.question.toPlainText() == "尚未发送的问题"
    calls = []
    def ask(collection_id, question, session_id, **kwargs):
        calls.append((collection_id, question, session_id))
        raise RuntimeError("受控测试：已核对请求目标")
    runtime.answer_service = lambda: SimpleNamespace(ask=ask)
    page.ask()
    QThreadPool.globalInstance().waitForDone(3000)
    APPLICATION.processEvents()
    assert calls == [(second.id, "尚未发送的问题", None)]
    assert not page.busy
    assert page.switch_collection.isEnabled()
    window.close()


def test_chat_busy_updates_top_bar_and_collection_lock() -> None:
    window = MainWindow(_Runtime())
    try:
        window._chat_busy_changed(True)
        assert window.top_bar.task_status.text() == "正在回答问题"
        assert window.collection_context.locked
        assert not window.collections_page.isEnabled()
        window._chat_busy_changed(False)
        assert window.top_bar.task_status.text() == "后台空闲"
        assert not window.collection_context.locked
        assert window.collections_page.isEnabled()
    finally:
        window.close()
        APPLICATION.processEvents()


def test_cancel_collection_switch_preserves_current_chat(monkeypatch):
    window = MainWindow(_Runtime())
    window.collections_page.collections.setCurrentRow(0)
    page = window.chat_page
    page._add_bubble("assistant", "保留回答")
    page.question.setPlainText("保留草稿")
    generation = window.collection_context.generation
    def cancel(*args):
        assert args[4] == 0  # Current collection is selected by default.
        return "", False
    monkeypatch.setattr(QInputDialog, "getItem", cancel)
    page.switch_collection.click()
    assert window.collection_context.generation == generation
    assert "保留回答" in page.transcript.toPlainText()
    assert page.question.toPlainText() == "保留草稿"
    window.close()


def test_choosing_current_collection_keeps_conversation(monkeypatch):
    runtime = _Runtime()
    window = MainWindow(runtime)
    window.collections_page.collections.setCurrentRow(0)
    page = window.chat_page
    bubble = page._add_bubble("assistant", "保留当前对话")
    generation = page.generation
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (runtime.collection_api.items[0].name, True))
    page.switch_collection.click()
    assert page.transcript.messages == [bubble]
    assert page.generation == window.collection_context.generation == generation
    window.close()


def test_no_collections_routes_to_creation_page():
    runtime = _Runtime()
    runtime.collection_api.items.clear()
    window = MainWindow(runtime)
    window.navigation.select_page(3)
    assert window.chat_page.collection_label.text() == "当前提问集合：未选择"
    assert window.chat_page.switch_collection.text() == "选择集合"
    window.chat_page.switch_collection.click()
    assert window.pages.currentIndex() == 1
    assert "新建集合" in window.collections_page.feedback.text()
    window.close()


def test_collection_read_failure_keeps_existing_context(monkeypatch):
    runtime = _Runtime()
    window = MainWindow(runtime)
    window.collections_page.collections.setCurrentRow(0)
    before = window.collection_context.collection_id
    def fail():
        raise OSError("private path")
    monkeypatch.setattr(runtime.collection_api, "list_all", fail)
    window.chat_page.switch_collection.click()
    assert "读取知识集合失败" in window.chat_page.feedback.text()
    assert window.chat_page.collection_id == before
    assert window.chat_page.collection_label.text() == "当前提问集合：人工智能"
    window.close()


def test_collection_disappearing_during_selection_clears_stale_target(monkeypatch):
    runtime = _Runtime()
    window = MainWindow(runtime)
    window.collections_page.collections.setCurrentRow(0)
    selected = runtime.collection_api.items[0]
    def remove_and_choose(*args):
        runtime.collection_api.items.clear()
        return selected.name, True
    monkeypatch.setattr(QInputDialog, "getItem", remove_and_choose)
    window.chat_page.switch_collection.click()
    assert window.collection_context.collection_id is None
    assert window.chat_page.collection_id is None
    assert "未选择" in window.chat_page.collection_label.text()
    assert "已不存在" in window.chat_page.feedback.text()
    window.close()


def test_refresh_preserves_collection_identity_after_rename():
    runtime = _Runtime()
    window = MainWindow(runtime)
    window.collections_page.collections.setCurrentRow(0)
    renamed = runtime.collection_api.items[0].model_copy(update={"name": "<b>资料</b>" + "长名称" * 20})
    runtime.collection_api.items[0] = renamed
    window.collections_page.refresh()
    assert window.chat_page.collection_id == renamed.id
    assert window.chat_page.collection_label.text() == f"当前提问集合：{renamed.name}"
    assert window.chat_page.collection_label.textFormat() == Qt.TextFormat.PlainText
    window.close()


def test_window_chat_blocks_collection_switch_and_defers_close():
    from types import SimpleNamespace
    import time
    started, release = Event(), Event()
    runtime = _Runtime()
    def ask(*args, should_cancel, **kwargs):
        started.set()
        assert release.wait(5)
        assert should_cancel()
        raise RuntimeError("已停止")
    runtime.answer_service = lambda: SimpleNamespace(ask=ask)
    window = MainWindow(runtime)
    window.show()
    window.collections_page.collections.setCurrentRow(0)
    page = window.chat_page
    original = window.collection_context.collection_id
    page.question.setPlainText("question")
    page.ask()
    try:
        assert started.wait(5)
        assert window.collection_context.locked
        assert not window.collections_page.isEnabled()
        window.collection_context.select(None, "other")
        assert window.collection_context.collection_id == original
        assert not window.close()
        assert page._cancel.is_set()
    finally:
        release.set()
        deadline = time.monotonic() + 5
        while page.busy and time.monotonic() < deadline:
            APPLICATION.processEvents()
            time.sleep(.005)
        assert not page.busy
        assert not window.collection_context.locked
        window.close()


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
    tabs = window.pages.widget(5).states.currentWidget()
    assert tabs.count() == 5
    assert tabs.tabText(4) == "备份与恢复"
    assert tabs.tabText(3) == "索引维护"
    window.close()
