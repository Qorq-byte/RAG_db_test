"""Overview and knowledge-library pages for the desktop workbench."""

from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ragdb.desktop.components import PageShell, StatCard, StatusBadge
from ragdb.desktop.workers import BackgroundTask


class OverviewPage(PageShell):
    def __init__(self, runtime) -> None:
        super().__init__("概览", "从资料进入学习，再把证据沉淀为可复用的知识。")
        self.runtime = runtime
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.source_count = StatCard("资料", "—")
        self.session_count = StatCard("问答会话", "—")
        self.artifact_count = StatCard("学习产物", "—")
        self.task_count = StatCard("最近任务", "—")
        for card in (
            self.source_count,
            self.session_count,
            self.artifact_count,
            self.task_count,
        ):
            cards.addWidget(card)
        layout.addLayout(cards)
        activity = QFrame()
        activity.setProperty("card", True)
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(18, 16, 18, 16)
        activity_layout.addWidget(QLabel("当前知识空间"))
        self.summary = QLabel("请选择或创建知识集合。")
        self.summary.setStyleSheet("font-size: 20px; font-weight: 650;")
        self.guidance = QLabel("在“集合与资料”中选择集合后，这里会显示它的学习进度。")
        self.guidance.setProperty("muted", True)
        self.guidance.setWordWrap(True)
        activity_layout.addWidget(self.summary)
        activity_layout.addWidget(self.guidance)
        layout.addWidget(activity)
        layout.addStretch()
        self.set_content(content)

    def show_collection(self, collection_id, name: str, _generation: int) -> None:
        self.summary.setText(f"当前集合：{name}")
        self.guidance.setText("资料已成为检索、问答与学习产物的共同证据源。")
        collections = self.runtime.collection_service().list_all()
        collection = next(
            (item for item in collections if item.id == collection_id), None
        )
        sources = (
            self.runtime.source_service().list_for_collection(collection)
            if collection
            else []
        )
        self.source_count.value.setText(str(len(sources)))
        stores = (
            (self.session_count, self.runtime.conversations),
            (self.artifact_count, self.runtime.artifacts),
            (self.task_count, self.runtime.tasks),
        )
        for card, store in stores:
            try:
                card.value.setText(str(len(store.list_for_collection(collection_id))))
            except (AttributeError, TypeError):
                card.value.setText("—")


class CollectionsPage(PageShell):
    collection_selected = Signal(object, str)

    def __init__(self, runtime) -> None:
        super().__init__("集合与资料", "组织证据源，并跟踪每份资料的处理状态。")
        self.runtime = runtime
        self._tasks = set()
        create = QPushButton("新建集合")
        create.setProperty("primary", True)
        delete = QPushButton("删除集合")
        delete.setProperty("danger", True)
        refresh = QPushButton("刷新")
        import_button = QToolButton()
        import_button.setText("导入资料")
        import_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(import_button)
        for label, callback in (
            ("文件", self.import_file),
            ("目录", self.import_directory),
            ("文本", self.import_text),
            ("网页", self.import_web),
            ("GitHub 仓库", self.import_repository),
        ):
            menu.addAction(label, callback)
        import_button.setMenu(menu)
        self.feedback = StatusBadge("就绪", "success")
        for widget in (self.feedback, refresh, delete, import_button, create):
            self.actions.addWidget(widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        collection_panel = QFrame()
        collection_panel.setProperty("card", True)
        collection_panel.setMinimumWidth(220)
        collection_panel.setMaximumWidth(320)
        left = QVBoxLayout(collection_panel)
        left.addWidget(QLabel("知识集合"))
        self.collections = QListWidget()
        self.collections.setSpacing(3)
        left.addWidget(self.collections, 1)
        source_panel = QFrame()
        source_panel.setProperty("card", True)
        right = QVBoxLayout(source_panel)
        source_header = QHBoxLayout()
        source_header.addWidget(QLabel("资料清单"))
        source_header.addStretch()
        delete_source = QPushButton("删除资料")
        delete_source.setProperty("danger", True)
        source_header.addWidget(delete_source)
        right.addLayout(source_header)
        self.sources = QTableWidget(0, 3)
        self.sources.setHorizontalHeaderLabels(("资料", "类型", "状态"))
        self.sources.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.sources.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sources.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.sources.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.sources.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        right.addWidget(self.sources, 1)
        splitter.addWidget(collection_panel)
        splitter.addWidget(source_panel)
        splitter.setStretchFactor(1, 1)
        self.set_content(splitter)

        create.clicked.connect(self.create_collection)
        delete.clicked.connect(self.delete_collection)
        refresh.clicked.connect(self.refresh)
        delete_source.clicked.connect(self.delete_source)
        self.collections.currentItemChanged.connect(self._select)
        self.refresh()

    def refresh(self) -> None:
        selected = (
            self.collections.currentItem().text()
            if self.collections.currentItem()
            else None
        )
        self.collections.clear()
        for collection in self.runtime.collection_service().list_all():
            item = QListWidgetItem(collection.name)
            item.setData(Qt.ItemDataRole.UserRole, collection)
            self.collections.addItem(item)
            if collection.name == selected:
                self.collections.setCurrentItem(item)
        self.feedback.setText(f"{self.collections.count()} 个集合")

    def create_collection(self) -> None:
        name, accepted = QInputDialog.getText(self, "新建集合", "集合名称")
        if accepted and name.strip():
            try:
                self.runtime.collection_service().create(name.strip())
            except Exception as error:
                QMessageBox.critical(self, "创建失败", str(error))
            self.refresh()

    def delete_collection(self) -> None:
        item = self.collections.currentItem()
        if (
            item is None
            or QMessageBox.question(
                self, "确认删除", "将删除集合及其全部索引，是否继续？"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.runtime.collection_service().delete_by_name(item.text())
        except Exception as error:
            QMessageBox.critical(self, "删除失败", str(error))
        self.refresh()

    def _select(self, current, _previous) -> None:
        self.sources.setRowCount(0)
        if current is None:
            return
        collection = current.data(Qt.ItemDataRole.UserRole)
        self.collection_selected.emit(collection.id, collection.name)
        for source in self.runtime.source_service().list_for_collection(collection):
            row = self.sources.rowCount()
            self.sources.insertRow(row)
            title = QTableWidgetItem(source.title)
            title.setData(Qt.ItemDataRole.UserRole, source)
            self.sources.setItem(row, 0, title)
            self.sources.setItem(row, 1, QTableWidgetItem(source.source_type.value))
            self.sources.setItem(row, 2, QTableWidgetItem(source.status.value))

    def _collection(self):
        item = self.collections.currentItem()
        if item is None:
            QMessageBox.information(self, "请选择集合", "请先选择一个知识集合。")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _run(self, collection, function) -> None:
        self.feedback.setText("正在导入…")
        self.feedback.setProperty("status", "warning")
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)
        task = BackgroundTask(collection.id, function)
        self._tasks.add(task)
        task.signals.succeeded.connect(self._import_finished)
        task.signals.failed.connect(self._import_failed)
        task.signals.finished.connect(
            lambda _token, current=task: self._tasks.discard(current)
        )
        QThreadPool.globalInstance().start(task)

    def _import_failed(self, _token, error: str) -> None:
        self.feedback.setText(f"导入失败：{error}")
        self.feedback.setProperty("status", "failure")

    def _import_finished(self, collection_id, _result) -> None:
        self.feedback.setText("导入完成")
        self.feedback.setProperty("status", "success")
        item = self.collections.currentItem()
        current = item.data(Qt.ItemDataRole.UserRole) if item else None
        if current is not None and current.id == collection_id:
            self._select(item, None)

    def import_file(self) -> None:
        collection = self._collection()
        path, _ = QFileDialog.getOpenFileName(self, "导入文件")
        if collection and path:
            self._run(
                collection,
                lambda: self.runtime.ingestion_service().ingest_file(
                    collection, Path(path)
                ),
            )

    def import_directory(self) -> None:
        collection = self._collection()
        path = QFileDialog.getExistingDirectory(self, "导入目录")
        if collection and path:
            self._run(
                collection,
                lambda: self.runtime.ingestion_service().ingest_directory(
                    collection, Path(path)
                ),
            )

    def import_text(self) -> None:
        collection = self._collection()
        text, accepted = QInputDialog.getMultiLineText(self, "导入文本", "内容")
        if collection and accepted and text.strip():
            self._run(
                collection,
                lambda: self.runtime.ingestion_service().ingest_text(
                    collection, text, "手动文本"
                ),
            )

    def import_web(self) -> None:
        collection = self._collection()
        url, accepted = QInputDialog.getText(self, "导入网页", "URL")
        if collection and accepted and url.strip():
            self._run(
                collection, lambda: self.runtime.ingest_web(collection, url.strip())
            )

    def import_repository(self) -> None:
        collection = self._collection()
        url, accepted = QInputDialog.getText(self, "导入 GitHub", "公开仓库 URL")
        if collection and accepted and url.strip():
            self._run(
                collection,
                lambda: self.runtime.ingest_repository(collection, url.strip()),
            )

    def delete_source(self) -> None:
        row = self.sources.currentRow()
        item = self.sources.item(row, 0) if row >= 0 else None
        if (
            item is None
            or QMessageBox.question(self, "确认删除", "将删除资料及其索引，是否继续？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.runtime.source_service().delete(item.data(Qt.ItemDataRole.UserRole).id)
            self._select(self.collections.currentItem(), None)
        except Exception as error:
            QMessageBox.critical(self, "删除失败", str(error))
