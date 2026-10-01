"""Main desktop workbench window."""

from PySide6.QtCore import QPoint, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ragdb.desktop.pages import CollectionsPage, OverviewPage
from ragdb.desktop.study_pages import ArtifactsPage, ChatPage, SearchPage
from ragdb.desktop.operations_page import OperationsPage
from ragdb.desktop.model_settings_page import ModelSettingsPage
from ragdb.desktop.components import DetailPanel
from ragdb.desktop.navigation import SidebarWidget, TopBar
from ragdb.desktop.theme import ThemeManager
from ragdb.desktop.chat_widgets import ConversationView
from ragdb.desktop.profile import ProfileDialog, ProfileStore, add_profile_menu_row


PAGES = ("概览", "集合与资料", "检索", "问答", "学习产物", "任务与诊断", "模型设置")


class CollectionContext(QWidget):
    changed = Signal(object, str, int)

    def __init__(self) -> None:
        super().__init__()
        self.collection_id = None
        self.collection_name = ""
        self.generation = 0
        self.locked = False

    def select(self, collection_id, name: str) -> None:
        if self.locked:
            return
        self.collection_id, self.collection_name = collection_id, name
        self.generation += 1
        self.changed.emit(collection_id, name, self.generation)


class MainWindow(QMainWindow):
    logout_requested = Signal()
    account_deletion_requested = Signal(str)

    def __init__(self, runtime=None, theme_manager: ThemeManager | None = None,
                 session=None) -> None:
        super().__init__()
        self.runtime = runtime
        self.session = session
        self.account_email = session.email if session is not None else ""
        account_dir = getattr(getattr(runtime, "settings", None), "storage", None)
        self.profile_store = ProfileStore(account_dir.data_dir if account_dir is not None else None)
        self.theme_manager = theme_manager or ThemeManager()
        self.setWindowTitle("ragdb 学习工作台")
        self.resize(1280, 800)
        self.collection_context = CollectionContext()
        self.navigation = SidebarWidget(
            self.theme_manager.reduce_motion,
            expanded_width=self.theme_manager.sidebar_width(),
            collapsed=self.theme_manager.sidebar_collapsed(),
            footer_visible=self.theme_manager.sidebar_footer_visible(),
        )
        self.pages = QStackedWidget()
        self.detail_panel = DetailPanel()
        self._detail_panel_preference = self.theme_manager.detail_panel_visible()
        self._narrow_layout = False
        self.details = self.detail_panel.content
        self.top_bar = TopBar(self.theme_manager)
        self.collection_context.changed.connect(
            lambda _id, name, _generation: self.navigation.collection.setText(name)
        )
        self.collection_context.changed.connect(self.top_bar.set_collection)
        self.collection_context.changed.connect(lambda *_: self.refresh_navigation_counts())
        for index, name in enumerate(PAGES):
            if runtime is not None and index == 0:
                page = OverviewPage(runtime)
                self.overview_page = page
                self.collection_context.changed.connect(page.show_collection)
                self.pages.addWidget(page)
                continue
            if runtime is not None and index == 1:
                page = CollectionsPage(runtime)
                self.collections_page = page
                page.collection_selected.connect(self.collection_context.select)
                self.pages.addWidget(page)
                continue
            if runtime is not None and index in (2, 3, 4):
                page_type = {2: SearchPage, 3: ChatPage, 4: ArtifactsPage}[index]
                page = page_type(runtime)
                if index == 3:
                    self.chat_page = page
                    page.busy_changed.connect(self._chat_busy_changed)
                    page.collection_switch_requested.connect(self.choose_chat_collection)
                if index == 4:
                    self.artifacts_page = page
                    page.count_changed.connect(self.refresh_navigation_counts)
                self.collection_context.changed.connect(page.set_collection)
                page.details_requested.connect(self.detail_panel.show_text)
                self.pages.addWidget(page)
                continue
            if runtime is not None and index == 5:
                page = OperationsPage(runtime)
                self.operations_page = page
                self.collection_context.changed.connect(page.set_collection)
                self.collections_page.records_changed.connect(page.refresh)
                self.pages.addWidget(page)
                continue
            if runtime is not None and index == 6:
                page = ModelSettingsPage(runtime)
                self.model_settings_page = page
                self.pages.addWidget(page)
                continue
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel(name)
            title.setObjectName("pageTitle")
            layout.addWidget(title)
            layout.addStretch()
            self.pages.addWidget(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.pages)
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(0, 1)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.addWidget(self.top_bar)
        content_layout.addWidget(splitter, 1)
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.navigation)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)
        self.navigation.page_selected.connect(self.select_page)
        self._create_profile_menu()
        self.navigation.user_collapsed_changed.connect(
            self.theme_manager.set_sidebar_collapsed
        )
        self.navigation.width_adjusted.connect(self.theme_manager.set_sidebar_width)
        self.navigation.footer_visibility_changed.connect(self.theme_manager.set_sidebar_footer_visible)
        self.theme_manager.changed.connect(self.navigation.update_motion_preference)
        self.navigation.update_motion_preference(self.theme_manager.resolved_mode().value, self.theme_manager.reduce_motion)
        self.top_bar.detail_toggled.connect(self.toggle_detail_preference)
        self.detail_panel.closed.connect(self.close_detail_preference)
        self._shortcuts = self._create_shortcuts()
        self.navigation.select_page(0)
        self.navigation_count_timer = QTimer(self)
        self.navigation_count_timer.setInterval(2000)
        self.navigation_count_timer.timeout.connect(self.refresh_navigation_counts)
        self.refresh_navigation_counts()
        self._apply_responsive_layout()
        self.statusBar().showMessage("就绪")
        self.logout_button = QPushButton("退出登录")
        self.logout_button.setAccessibleName("退出当前账号")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.statusBar().addPermanentWidget(self.logout_button)

    def _create_profile_menu(self) -> None:
        self.profile_menu = QMenu(self)
        self.profile_menu.setObjectName("profileMenu")
        self.profile_menu.setMinimumWidth(284)
        self.profile_action, self.profile_row = add_profile_menu_row(
            self.profile_menu, "个人资料", "profile"
        )
        self.model_action, self.model_row = add_profile_menu_row(
            self.profile_menu, "模型", "model"
        )
        self.settings_action, self.settings_row = add_profile_menu_row(
            self.profile_menu, "设置", "settings"
        )
        self.profile_menu.addSeparator()
        self.signout_action, self.signout_row = add_profile_menu_row(
            self.profile_menu, "退出登录", "logout", danger=True
        )
        self.profile_action.triggered.connect(self.open_profile)
        self.model_action.triggered.connect(lambda: self.navigation.select_page(6))
        self.settings_action.triggered.connect(self.open_account_settings)
        self.signout_action.triggered.connect(self.logout_requested.emit)
        self.profile_menu.aboutToShow.connect(self._refresh_profile_menu)
        self.profile_menu.aboutToShow.connect(lambda: self.navigation.profile_button.set_menu_open(True))
        self.profile_menu.aboutToHide.connect(lambda: self.navigation.profile_button.set_menu_open(False))
        self.theme_manager.changed.connect(lambda *_: self._refresh_profile_menu())
        self.navigation.profile_requested.connect(self._show_profile_menu)
        self._refresh_profile_button()
        self._refresh_profile_menu()

    def _refresh_profile_button(self) -> None:
        self.navigation.profile_button.set_profile(
            self.profile_store.load(), self.account_email, self.profile_store.avatar()
        )

    def _refresh_profile_menu(self) -> None:
        dark = self.theme_manager.resolved_mode().value == "dark"
        for row in (self.profile_row, self.model_row, self.settings_row, self.signout_row):
            row.set_dark_mode(dark)
        settings = getattr(self.runtime, "settings", None)
        if settings is not None:
            from ragdb.desktop.model_settings_page import model_caption
            self.model_row.set_value(model_caption(settings.chat))
        else:
            self.model_row.set_value("")

    def _show_profile_menu(self) -> None:
        button = self.navigation.profile_button
        point = button.mapToGlobal(QPoint(0, button.height() + 4))
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is not None:
            bounds = screen.availableGeometry()
            width = self.profile_menu.sizeHint().width()
            height = self.profile_menu.sizeHint().height()
            point.setX(max(bounds.left() + 8, min(point.x(), bounds.right() - width - 8)))
            if point.y() + height > bounds.bottom() - 8:
                point.setY(button.mapToGlobal(QPoint(0, 0)).y() - height - 4)
        self.profile_menu.popup(point)

    def open_profile(self) -> None:
        dialog = ProfileDialog(self.profile_store, self.account_email, self)
        dialog.saved.connect(lambda _profile: self._refresh_profile_button())
        dialog.exec()

    def open_account_settings(self) -> None:
        from ragdb.desktop.account_settings import AccountSettingsDialog

        auth_settings = getattr(getattr(self.runtime, "settings", None), "auth", None)
        dialog = AccountSettingsDialog(self.theme_manager, self.account_email,
                                       auth_settings, self)
        dialog.logout_requested.connect(self.logout_requested.emit)
        dialog.delete_requested.connect(self.account_deletion_requested.emit)
        dialog.exec()

    def select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.top_bar.set_page(PAGES[index])
        self._apply_detail_visibility(index in (2, 3, 4))
        self.refresh_navigation_counts()

    def refresh_navigation_counts(self) -> None:
        if self.runtime is None:
            return
        try:
            total = len(self.runtime.collections.list_all())
            self.navigation.collection_count.setText(str(total))
            self.navigation.collection_count.setToolTip(f"知识集合总数：{total}")
        except Exception:
            self.navigation.collection_count.setText("—")
            self.navigation.collection_count.setToolTip("知识集合数量暂不可用")
        collection_id = self.collection_context.collection_id
        if collection_id is None:
            self.navigation.buttons[4].set_count(None)
            return
        try:
            self.navigation.buttons[4].set_count(
                len(self.runtime.artifacts.list_for_collection(collection_id))
            )
        except Exception:
            self.navigation.buttons[4].set_count(None)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_navigation_counts()
        self.navigation_count_timer.start()

    def hideEvent(self, event) -> None:
        self.navigation_count_timer.stop()
        super().hideEvent(event)

    def _chat_busy_changed(self, busy):
        self.collection_context.locked = busy
        self.collections_page.setEnabled(not busy)
        self.top_bar.task_status.setText("正在回答问题" if busy else "后台空闲")

    def choose_chat_collection(self):
        if self.chat_page.busy or self.collection_context.locked:
            return
        try:
            collections = list(self.runtime.collections.list_all())
        except Exception:
            self.chat_page.feedback.setText("读取知识集合失败，请稍后重试。")
            return
        if not collections:
            self.navigation.select_page(1)
            self.collections_page.feedback.setText("暂无知识集合，请先点击“新建集合”。")
            return
        current = next((index for index, collection in enumerate(collections)
                        if collection.id == self.collection_context.collection_id), 0)
        name, accepted = QInputDialog.getItem(
            self, "切换提问集合", "选择知识集合", [item.name for item in collections], current, False,
        )
        if not accepted or self.chat_page.busy or self.collection_context.locked:
            return
        selected = next((item for item in collections if item.name == name), None)
        if selected is None:
            return
        try:
            if selected.id == self.collection_context.collection_id:
                # Keep retry tokens valid when the user confirms the same collection.
                current_collection = next((item for item in self.runtime.collections.list_all()
                                           if item.id == selected.id), None)
                if current_collection is not None and current_collection.name == self.collection_context.collection_name:
                    self.chat_page.question.setFocus()
                    return
            found = self.collections_page.refresh(selected_id=selected.id)
        except Exception:
            self.chat_page.feedback.setText("刷新知识集合失败，请稍后重试。")
            return
        if not found:
            self.chat_page.feedback.setText("所选集合已不存在，请重新选择。")
            return
        self.chat_page.question.setFocus()

    def toggle_detail_preference(self) -> None:
        self.set_detail_preference(not self._detail_panel_preference)

    def close_detail_preference(self) -> None:
        self.set_detail_preference(False)

    def set_detail_preference(self, visible: bool) -> None:
        self._detail_panel_preference = visible
        self.theme_manager.set_detail_panel_visible(visible)
        self._apply_detail_visibility(self.pages.currentIndex() in (2, 3, 4))

    def _apply_detail_visibility(self, page_supports_details: bool) -> None:
        self.detail_panel.setVisible(
            page_supports_details
            and self._detail_panel_preference
            and not self._narrow_layout
        )

    def _apply_responsive_layout(self) -> None:
        narrow = self.width() < 1100
        if narrow == self._narrow_layout:
            return
        self._narrow_layout = narrow
        if narrow:
            self.navigation.set_collapsed(True)
        else:
            self.navigation.set_collapsed(self.theme_manager.sidebar_collapsed())
        self._apply_detail_visibility(self.pages.currentIndex() in (2, 3, 4))

    def _create_shortcuts(self) -> tuple[QShortcut, ...]:
        shortcuts = []
        for index in range(len(PAGES)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(
                lambda target=index: self._select_page_from_shortcut(target)
            )
            shortcuts.append(shortcut)
        toggle = QShortcut(QKeySequence("Ctrl+B"), self)
        toggle.activated.connect(self._toggle_sidebar_from_shortcut)
        shortcuts.append(toggle)
        return tuple(shortcuts)

    def _can_use_window_shortcut(self) -> bool:
        return not isinstance(QApplication.focusWidget(), (QTextEdit, ConversationView))

    def _select_page_from_shortcut(self, index: int) -> None:
        if self._can_use_window_shortcut():
            self.navigation.select_page(index)

    def _toggle_sidebar_from_shortcut(self) -> None:
        if self._can_use_window_shortcut() and not self._narrow_layout:
            self.navigation.toggle_collapsed()

    def handle_escape(self) -> bool:
        if self.detail_panel.isVisible():
            self.close_detail_preference()
            return True
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.reject()
            return True
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.handle_escape():
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def closeEvent(self, event) -> None:
        chat_page = getattr(self, "chat_page", None)
        if chat_page is not None and chat_page.busy:
            chat_page.cancel()
            self.statusBar().showMessage("已请求停止问答，请等待操作结束后关闭窗口。")
            event.ignore()
            return
        operations_page = getattr(self, "operations_page", None)
        if operations_page is not None and (operations_page.index_maintenance.busy or operations_page.backup.busy):
            self.statusBar().showMessage("索引维护尚未结束，请等待完成后关闭窗口。")
            event.ignore()
            return
        settings_page = getattr(self, "model_settings_page", None)
        if settings_page is not None and settings_page.busy:
            if settings_page._action == "rebuild":
                settings_page.cancel_rebuild()
            self.statusBar().showMessage("模型操作尚未结束，请等待完成后关闭窗口。")
            event.ignore()
            return
        QThreadPool.globalInstance().waitForDone(5000)
        event.accept()
