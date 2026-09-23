"""Main desktop workbench window."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QMainWindow, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget
from ragdb.desktop.pages import CollectionsPage, OverviewPage


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
    def __init__(self, runtime=None) -> None:
        super().__init__()
        self.runtime = runtime
        self.setWindowTitle("ragdb 学习工作台")
        self.resize(1280, 800)
        self.collection_context = CollectionContext()
        self.navigation = QListWidget()
        self.navigation.addItems(PAGES)
        self.navigation.setFixedWidth(180)
        self.pages = QStackedWidget()
        for index, name in enumerate(PAGES):
            if runtime is not None and index == 0:
                page = OverviewPage()
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
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel(name)
            title.setObjectName("pageTitle")
            layout.addWidget(title)
            layout.addStretch()
            self.pages.addWidget(page)
        self.details = QTextBrowser()
        self.details.setPlaceholderText("选择资料、检索结果或引用后在此查看详情")
        self.details.setMinimumWidth(280)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.navigation)
        splitter.addWidget(self.pages)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage("就绪")
