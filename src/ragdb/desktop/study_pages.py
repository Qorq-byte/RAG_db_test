"""Search, chat, and learning artifact pages."""

from PySide6.QtCore import QThreadPool, Qt, Signal, QSize
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ragdb.desktop.components import PageShell, ResultCard, StatusBadge
from ragdb.desktop.workers import BackgroundTask
from ragdb.domain.enums import ArtifactType


class AsyncPage(PageShell):
    details_requested = Signal(str)

    def __init__(self, runtime, title: str, description: str) -> None:
        super().__init__(title, description)
        self.runtime = runtime
        self.collection_id = None
        self.generation = 0
        self._tasks = set()
        self._task_in_flight = False
        self.feedback = StatusBadge("等待操作", "success")
        self.actions.addWidget(self.feedback)

    def set_collection(self, collection_id, _name: str, generation: int) -> None:
        self.collection_id, self.generation = collection_id, generation

    def _set_feedback(self, text: str, status: str) -> None:
        self.feedback.setText(text)
        self.feedback.setProperty("status", status)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def run_task(self, function, success, trigger=None, success_message: str = "已完成") -> bool:
        if self._task_in_flight:
            self._set_feedback("当前操作尚未完成", "warning")
            return False
        token = (self.collection_id, self.generation)
        self._task_in_flight = True
        if trigger is not None:
            trigger.setEnabled(False)
        self._set_feedback("处理中…", "warning")
        task = BackgroundTask(token, function)
        self._tasks.add(task)

        def completed(current, result):
            if current == (self.collection_id, self.generation):
                success(result)
                self._set_feedback(success_message, "success")

        def failed(current, error):
            if current == (self.collection_id, self.generation):
                self._set_feedback(f"失败：{error}", "failure")

        task.signals.succeeded.connect(completed)
        task.signals.failed.connect(failed)
        def finished(_token, current=task):
            self._tasks.discard(current)
            self._task_in_flight = False
            if trigger is not None:
                trigger.setEnabled(True)

        task.signals.finished.connect(finished)
        QThreadPool.globalInstance().start(task)
        return True

    def require_collection(self) -> bool:
        if self.collection_id is None:
            self._set_feedback("请先选择知识集合", "warning")
            return False
        return True


class SearchPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime, "检索", "用关键词定位资料中的原始证据。")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        search_bar = QFrame()
        search_bar.setProperty("card", True)
        row = QHBoxLayout(search_bar)
        self.query = QLineEdit()
        self.query.setPlaceholderText("搜索概念、事实或代码符号")
        self.search_button = QPushButton("检索")
        self.search_button.setProperty("primary", True)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        layout.addWidget(search_bar)
        self.result_caption = QLabel("结果会按相关性排序，并保留来源位置。")
        self.result_caption.setProperty("muted", True)
        layout.addWidget(self.result_caption)
        self.results = QListWidget()
        self.results.setSpacing(8)
        layout.addWidget(self.results, 1)
        self.set_content(content)
        self.search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        self.results.currentItemChanged.connect(self.show_details)

    def search(self) -> None:
        if not self.require_collection() or not self.query.text().strip():
            return
        query, collection_id = self.query.text().strip(), self.collection_id
        self.run_task(
            lambda: self.runtime.search_service().search(collection_id, query),
            self.show_results,
            self.search_button,
            "检索完成",
        )

    def show_results(self, hits) -> None:
        self.results.clear()
        self.result_caption.setText(f"找到 {len(hits)} 条证据")
        for hit in hits:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, hit)
            item.setSizeHint(QSize(0, 104))
            self.results.addItem(item)
            metadata = f"#{hit.rank}  ·  {hit.source_uri}"
            self.results.setItemWidget(
                item, ResultCard(hit.source_title, hit.text[:190], metadata)
            )
        if not hits:
            self.result_caption.setText(
                "没有找到证据。请尝试更具体的关键词，或先导入相关资料。"
            )

    def show_details(self, current, _previous) -> None:
        if current is None:
            return
        hit = current.data(Qt.ItemDataRole.UserRole)
        self.details_requested.emit(
            f"{hit.source_title}\n{hit.source_uri}\n\n{hit.text}\n\n位置：{hit.position.model_dump(exclude_none=True)}\n评分：{hit.scores.model_dump(exclude_none=True)}"
        )


class ChatPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime, "问答", "让答案引用当前集合中的可核验依据。")
        self.session_id = None
        new = QPushButton("新会话")
        self.actions.addWidget(new)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        session_bar = QFrame()
        session_bar.setProperty("card", True)
        session_layout = QHBoxLayout(session_bar)
        session_layout.addWidget(QLabel("会话"))
        self.sessions = QComboBox()
        session_layout.addWidget(self.sessions, 1)
        layout.addWidget(session_bar)
        self.transcript = QTextBrowser()
        self.transcript.setPlaceholderText("选择集合并提出问题，回答会在这里出现。")
        layout.addWidget(self.transcript, 1)
        composer = QFrame()
        composer.setProperty("card", True)
        row = QHBoxLayout(composer)
        self.question = QLineEdit()
        self.question.setPlaceholderText("向当前知识集合提问")
        self.ask_button = QPushButton("发送")
        self.ask_button.setProperty("primary", True)
        row.addWidget(self.question, 1)
        row.addWidget(self.ask_button)
        layout.addWidget(composer)
        self.set_content(content)
        self.sessions.currentIndexChanged.connect(self.select_session)
        self.ask_button.clicked.connect(self.ask)
        self.question.returnPressed.connect(self.ask)
        new.clicked.connect(self.new_session)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation)
        self.refresh_sessions()

    def refresh_sessions(self) -> None:
        self.sessions.blockSignals(True)
        self.sessions.clear()
        self.sessions.addItem("新会话", None)
        if self.collection_id:
            for session in self.runtime.conversations.list_for_collection(
                self.collection_id
            ):
                self.sessions.addItem(session.title or str(session.id), session.id)
        if self.session_id:
            index = self.sessions.findData(self.session_id)
            self.sessions.setCurrentIndex(max(0, index))
        self.sessions.blockSignals(False)

    def select_session(self, _index: int) -> None:
        self.session_id = self.sessions.currentData()
        self.transcript.clear()
        if self.session_id:
            for message in self.runtime.conversations.list_messages(self.session_id):
                self.transcript.append(
                    f"<b>{message.role.value}</b>：{message.content}"
                )

    def new_session(self) -> None:
        self.sessions.setCurrentIndex(0)
        self.session_id = None
        self.transcript.clear()
        self.question.setFocus()

    def ask(self) -> None:
        if not self.require_collection() or not self.question.text().strip():
            return
        question, collection_id, session_id = (
            self.question.text().strip(),
            self.collection_id,
            self.session_id,
        )
        self.question.clear()
        self.run_task(
            lambda: self.runtime.answer_service().ask(
                collection_id, question, session_id
            ),
            lambda answer: self.show_answer(question, answer),
            self.ask_button,
            "已收到回答",
        )

    def show_answer(self, question, answer) -> None:
        self.session_id = answer.conversation.id
        self.transcript.append(f"<p><b>你</b><br>{question}</p>")
        self.transcript.append(f"<p><b>ragdb</b><br>{answer.content}</p>")
        self.details_requested.emit(
            "\n".join(
                f"[{c.display_index}] {c.source_title}\n{c.source_uri}"
                for c in answer.citations
            )
        )
        self.refresh_sessions()


class ArtifactsPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime, "学习产物", "把检索证据整理为提纲、卡片和复习材料。")
        self.kind = QComboBox()
        for kind in ArtifactType:
            self.kind.addItem(kind.value, kind)
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("生成主题")
        self.topic.setMinimumWidth(200)
        self.generate_button = QPushButton("生成")
        self.generate_button.setProperty("primary", True)
        delete = QPushButton("删除")
        delete.setProperty("danger", True)
        for widget in (self.kind, self.topic, self.generate_button, delete):
            self.actions.addWidget(widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        history = QFrame()
        history.setProperty("card", True)
        history_layout = QVBoxLayout(history)
        history_layout.addWidget(QLabel("产物历史"))
        self.items = QListWidget()
        history_layout.addWidget(self.items, 1)
        preview = QFrame()
        preview.setProperty("card", True)
        preview_layout = QVBoxLayout(preview)
        preview_layout.addWidget(QLabel("内容预览"))
        self.content = QTextBrowser()
        self.content.setPlaceholderText("选择产物后查看内容与引用。")
        preview_layout.addWidget(self.content, 1)
        splitter.addWidget(history)
        splitter.addWidget(preview)
        splitter.setStretchFactor(1, 2)
        self.set_content(splitter)
        self.generate_button.clicked.connect(self.generate)
        delete.clicked.connect(self.delete)
        self.items.currentItemChanged.connect(self.show_artifact)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation)
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        self.content.clear()
        if self.collection_id:
            for artifact in self.runtime.artifacts.list_for_collection(
                self.collection_id
            ):
                item = QListWidgetItem(
                    f"{artifact.artifact_type.value}  ·  {artifact.title}"
                )
                item.setData(Qt.ItemDataRole.UserRole, artifact)
                self.items.addItem(item)

    def generate(self) -> None:
        if not self.require_collection() or not self.topic.text().strip():
            return
        topic, kind, collection_id = (
            self.topic.text().strip(),
            self.kind.currentData(),
            self.collection_id,
        )
        self.run_task(
            lambda: self.runtime.generation_service().generate(
                collection_id, kind, topic
            ),
            self.generated,
            self.generate_button,
            "已生成学习产物",
        )

    def generated(self, artifact) -> None:
        if artifact is None:
            self._set_feedback("证据不足，请补充资料或缩小主题", "warning")
            return
        self.refresh()

    def show_artifact(self, current, _previous) -> None:
        if current is None:
            return
        artifact = current.data(Qt.ItemDataRole.UserRole)
        self.content.setMarkdown(artifact.content)
        citations = self.runtime.artifacts.list_citations(artifact.id)
        self.details_requested.emit(
            "\n".join(
                f"[{c.display_index}] {c.source_title}\n{c.source_uri}"
                for c in citations
            )
        )

    def delete(self) -> None:
        item = self.items.currentItem()
        if (
            item is None
            or QMessageBox.question(self, "确认删除", "确认删除该学习产物？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.runtime.artifacts.delete(item.data(Qt.ItemDataRole.UserRole).id)
        self.refresh()
