"""Main desktop workbench window."""

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ragdb.desktop.pages import CollectionsPage, OverviewPage
from ragdb.desktop.study_pages import ArtifactsPage, ChatPage, SearchPage
from ragdb.desktop.operations_page import OperationsPage
from ragdb.desktop.components import DetailPanel
from ragdb.desktop.navigation import SidebarWidget, TopBar
from ragdb.desktop.theme import ThemeManager


PAGES = ("概览", "集合与资料", "检索", "问答", "学习产物", "任务与诊断")


class CollectionContext(QWidget):
    changed = Signal(object, str, int)

    def __init__(self) -> None:
        super().__init__()
        self.collection_id = None
        self.collection_name = ""
        self.generation = 0

    def select(self, collection_id, name: str) -> None:
        self.collection_id, self.collection_name = collection_id, name
        self.generation += 1
        self.changed.emit(collection_id, name, self.generation)


class MainWindow(QMainWindow):
    def __init__(self, runtime=None, theme_manager: ThemeManager | None = None) -> None:
        super().__init__()
        self.runtime = runtime
        self.theme_manager = theme_manager or ThemeManager()
        self.setWindowTitle("ragdb 学习工作台")
        self.resize(1280, 800)
        self.collection_context = CollectionContext()
        self.navigation = SidebarWidget(
            self.theme_manager.reduce_motion,
            expanded_width=self.theme_manager.sidebar_width(),
            collapsed=self.theme_manager.sidebar_collapsed(),
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
                self.collection_context.changed.connect(page.set_collection)
                page.details_requested.connect(self.detail_panel.show_text)
                self.pages.addWidget(page)
                continue
            if runtime is not None and index == 5:
                page = OperationsPage(runtime)
                self.collection_context.changed.connect(page.set_collection)
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
        self.navigation.user_collapsed_changed.connect(
            self.theme_manager.set_sidebar_collapsed
        )
        self.navigation.width_adjusted.connect(self.theme_manager.set_sidebar_width)
        self.top_bar.detail_toggled.connect(self.toggle_detail_preference)
        self.detail_panel.closed.connect(self.close_detail_preference)
        self._shortcuts = self._create_shortcuts()
        self.navigation.select_page(0)
        self._apply_responsive_layout()
        self.statusBar().showMessage("就绪")

    def select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.top_bar.set_page(PAGES[index])
        self._apply_detail_visibility(index in (2, 3, 4))

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
        return not isinstance(QApplication.focusWidget(), QTextEdit)

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
        QThreadPool.globalInstance().waitForDone(5000)
        event.accept()
