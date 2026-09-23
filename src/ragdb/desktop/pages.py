"""Core desktop workbench pages."""

from PySide6.QtCore import Qt, Signal
from pathlib import Path
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget
from ragdb.desktop.workers import BackgroundTask


class OverviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("概览"))
        self.summary = QLabel("请选择或创建知识集合。")
        layout.addWidget(self.summary)
        layout.addStretch()

    def show_collection(self, _collection_id, name: str, _generation: int) -> None:
        self.summary.setText(f"当前集合：{name}")


class CollectionsPage(QWidget):
    collection_selected = Signal(object, str)

    def __init__(self, runtime) -> None:
        super().__init__()
        self.runtime = runtime
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("集合与资料"))
        buttons = QHBoxLayout()
        create = QPushButton("新建集合")
        delete = QPushButton("删除集合")
        refresh = QPushButton("刷新")
        import_file = QPushButton("导入文件")
        import_directory = QPushButton("导入目录")
        import_text = QPushButton("导入文本")
        import_web = QPushButton("导入网页")
        import_repo = QPushButton("导入 GitHub")
        delete_source = QPushButton("删除资料")
        buttons.addWidget(create); buttons.addWidget(delete); buttons.addWidget(refresh); buttons.addStretch()
        layout.addLayout(buttons)
        imports = QHBoxLayout()
        for button in (import_file, import_directory, import_text, import_web, import_repo, delete_source): imports.addWidget(button)
        imports.addStretch(); layout.addLayout(imports)
        self.collections = QListWidget()
        self.sources = QListWidget()
        layout.addWidget(QLabel("知识集合")); layout.addWidget(self.collections)
        layout.addWidget(QLabel("资料")); layout.addWidget(self.sources)
        create.clicked.connect(self.create_collection)
        delete.clicked.connect(self.delete_collection)
        refresh.clicked.connect(self.refresh)
        import_file.clicked.connect(self.import_file)
        import_directory.clicked.connect(self.import_directory)
        import_text.clicked.connect(self.import_text)
        import_web.clicked.connect(self.import_web)
        import_repo.clicked.connect(self.import_repository)
        delete_source.clicked.connect(self.delete_source)
        self.collections.currentItemChanged.connect(self._select)
        self._tasks = set()
        self.refresh()

    def refresh(self) -> None:
        self.collections.clear()
        for collection in self.runtime.collection_service().list_all():
            item = QListWidgetItem(collection.name)
            item.setData(Qt.ItemDataRole.UserRole, collection)
            self.collections.addItem(item)

    def create_collection(self) -> None:
        name, accepted = QInputDialog.getText(self, "新建集合", "集合名称")
        if accepted and name.strip():
            try:
                self.runtime.collection_service().create(name)
            except Exception as error:
                QMessageBox.critical(self, "创建失败", str(error))
            self.refresh()

    def delete_collection(self) -> None:
        item = self.collections.currentItem()
        if item is None or QMessageBox.question(self, "确认删除", "将删除集合及其全部索引，是否继续？") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.runtime.collection_service().delete_by_name(item.text())
        except Exception as error:
            QMessageBox.critical(self, "删除失败", str(error))
        self.refresh()

    def _select(self, current, _previous) -> None:
        self.sources.clear()
        if current is None:
            return
        collection = current.data(Qt.ItemDataRole.UserRole)
        self.collection_selected.emit(collection.id, collection.name)
        for source in self.runtime.source_service().list_for_collection(collection):
            source_item = QListWidgetItem(f"{source.title}  ·  {source.status.value}")
            source_item.setData(Qt.ItemDataRole.UserRole, source)
            self.sources.addItem(source_item)

    def _collection(self):
        item = self.collections.currentItem()
        if item is None:
            QMessageBox.information(self, "请选择集合", "请先选择一个知识集合。")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _run(self, collection, function) -> None:
        task = BackgroundTask(collection.id, function)
        self._tasks.add(task)
        task.signals.succeeded.connect(self._import_finished)
        task.signals.failed.connect(lambda _token, error: QMessageBox.critical(self, "导入失败", error))
        task.signals.finished.connect(lambda _token, current=task: self._tasks.discard(current))
        QThreadPool.globalInstance().start(task)

    def _import_finished(self, collection_id, _result) -> None:
        item = self.collections.currentItem()
        current = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if current is not None and current.id == collection_id:
            self._select(self.collections.currentItem(), None)

    def import_file(self) -> None:
        collection = self._collection()
        path, _ = QFileDialog.getOpenFileName(self, "导入文件")
        if collection and path: self._run(collection, lambda: self.runtime.ingestion_service().ingest_file(collection, Path(path)))

    def import_directory(self) -> None:
        collection = self._collection()
        path = QFileDialog.getExistingDirectory(self, "导入目录")
        if collection and path: self._run(collection, lambda: self.runtime.ingestion_service().ingest_directory(collection, Path(path)))

    def import_text(self) -> None:
        collection = self._collection()
        text, accepted = QInputDialog.getMultiLineText(self, "导入文本", "内容")
        if collection and accepted and text.strip(): self._run(collection, lambda: self.runtime.ingestion_service().ingest_text(collection, text, "手动文本"))

    def import_web(self) -> None:
        collection = self._collection()
        url, accepted = QInputDialog.getText(self, "导入网页", "URL")
        if collection and accepted and url.strip(): self._run(collection, lambda: self.runtime.ingest_web(collection, url))

    def import_repository(self) -> None:
        collection = self._collection()
        url, accepted = QInputDialog.getText(self, "导入 GitHub", "公开仓库 URL")
        if collection and accepted and url.strip(): self._run(collection, lambda: self.runtime.ingest_repository(collection, url))

    def delete_source(self) -> None:
        item = self.sources.currentItem()
        if item is None or QMessageBox.question(self, "确认删除", "将删除资料及其索引，是否继续？") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.runtime.source_service().delete(item.data(Qt.ItemDataRole.UserRole).id)
            self._select(self.collections.currentItem(), None)
        except Exception as error:
            QMessageBox.critical(self, "删除失败", str(error))
