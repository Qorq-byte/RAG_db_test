"""Search, chat, and learning artifact pages."""

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ragdb.desktop.workers import BackgroundTask
from ragdb.domain.enums import ArtifactType


class AsyncPage(QWidget):
    details_requested = Signal(str)

    def __init__(self, runtime) -> None:
        super().__init__()
        self.runtime = runtime
        self.collection_id = None
        self.generation = 0
        self._tasks = set()

    def set_collection(self, collection_id, _name: str, generation: int) -> None:
        self.collection_id, self.generation = collection_id, generation

    def run_task(self, function, success) -> None:
        token = (self.collection_id, self.generation)
        task = BackgroundTask(token, function)
        self._tasks.add(task)
        task.signals.succeeded.connect(lambda completed, result: success(result) if completed == (self.collection_id, self.generation) else None)
        task.signals.failed.connect(lambda completed, error: QMessageBox.critical(self, "操作失败", error) if completed == (self.collection_id, self.generation) else None)
        task.signals.finished.connect(lambda _token, current=task: self._tasks.discard(current))
        QThreadPool.globalInstance().start(task)

    def require_collection(self) -> bool:
        if self.collection_id is None:
            QMessageBox.information(self, "请选择集合", "请先在“集合与资料”中选择知识集合。")
            return False
        return True


class SearchPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        layout = QVBoxLayout(self); layout.addWidget(QLabel("检索"))
        row = QHBoxLayout(); self.query = QLineEdit(); self.query.setPlaceholderText("输入检索内容")
        button = QPushButton("检索"); row.addWidget(self.query); row.addWidget(button); layout.addLayout(row)
        self.results = QListWidget(); layout.addWidget(self.results)
        button.clicked.connect(self.search); self.query.returnPressed.connect(self.search)
        self.results.currentItemChanged.connect(self.show_details)

    def search(self) -> None:
        if not self.require_collection() or not self.query.text().strip(): return
        query, collection_id = self.query.text().strip(), self.collection_id
        self.run_task(lambda: self.runtime.search_service().search(collection_id, query), self.show_results)

    def show_results(self, hits) -> None:
        self.results.clear()
        for hit in hits:
            item = QListWidgetItem(f"[{hit.rank}] {hit.source_title}\n{hit.text[:160]}")
            item.setData(256, hit); self.results.addItem(item)

    def show_details(self, current, _previous) -> None:
        if current is None: return
        hit = current.data(256)
        self.details_requested.emit(f"{hit.source_title}\n{hit.source_uri}\n\n{hit.text}\n\n位置：{hit.position.model_dump(exclude_none=True)}\n评分：{hit.scores.model_dump(exclude_none=True)}")


class ChatPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self.session_id = None
        layout = QVBoxLayout(self); layout.addWidget(QLabel("问答"))
        self.sessions = QComboBox(); self.sessions.currentIndexChanged.connect(self.select_session); layout.addWidget(self.sessions)
        self.transcript = QTextBrowser(); layout.addWidget(self.transcript)
        row = QHBoxLayout(); self.question = QLineEdit(); self.question.setPlaceholderText("向当前集合提问")
        ask = QPushButton("发送"); new = QPushButton("新会话"); row.addWidget(self.question); row.addWidget(ask); row.addWidget(new); layout.addLayout(row)
        ask.clicked.connect(self.ask); self.question.returnPressed.connect(self.ask); new.clicked.connect(self.new_session)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation); self.refresh_sessions()

    def refresh_sessions(self) -> None:
        self.sessions.clear(); self.sessions.addItem("新会话", None)
        if self.collection_id:
            for session in self.runtime.conversations.list_for_collection(self.collection_id): self.sessions.addItem(session.title or str(session.id), session.id)

    def select_session(self, _index: int) -> None:
        self.session_id = self.sessions.currentData(); self.transcript.clear()
        if self.session_id:
            for message in self.runtime.conversations.list_messages(self.session_id): self.transcript.append(f"<b>{message.role.value}</b>：{message.content}")

    def new_session(self) -> None:
        self.sessions.setCurrentIndex(0); self.session_id = None; self.transcript.clear()

    def ask(self) -> None:
        if not self.require_collection() or not self.question.text().strip(): return
        question, collection_id, session_id = self.question.text().strip(), self.collection_id, self.session_id
        self.question.clear(); self.run_task(lambda: self.runtime.answer_service().ask(collection_id, question, session_id), lambda answer: self.show_answer(question, answer))

    def show_answer(self, question, answer) -> None:
        self.session_id = answer.conversation.id
        self.transcript.append(f"<b>user</b>：{question}"); self.transcript.append(f"<b>assistant</b>：{answer.content}")
        self.details_requested.emit("\n".join(f"[{c.display_index}] {c.source_title}\n{c.source_uri}" for c in answer.citations))
        self.refresh_sessions()


class ArtifactsPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        layout = QVBoxLayout(self); layout.addWidget(QLabel("学习产物"))
        row = QHBoxLayout(); self.kind = QComboBox()
        for kind in ArtifactType: self.kind.addItem(kind.value, kind)
        self.topic = QLineEdit(); self.topic.setPlaceholderText("生成主题")
        generate = QPushButton("生成"); delete = QPushButton("删除")
        row.addWidget(self.kind); row.addWidget(self.topic); row.addWidget(generate); row.addWidget(delete); layout.addLayout(row)
        self.items = QListWidget(); self.content = QTextBrowser(); layout.addWidget(self.items); layout.addWidget(self.content)
        generate.clicked.connect(self.generate); delete.clicked.connect(self.delete); self.items.currentItemChanged.connect(self.show_artifact)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation); self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        if self.collection_id:
            for artifact in self.runtime.artifacts.list_for_collection(self.collection_id):
                item = QListWidgetItem(f"{artifact.artifact_type.value} · {artifact.title}"); item.setData(256, artifact); self.items.addItem(item)

    def generate(self) -> None:
        if not self.require_collection() or not self.topic.text().strip(): return
        topic, kind, collection_id = self.topic.text().strip(), self.kind.currentData(), self.collection_id
        self.run_task(lambda: self.runtime.generation_service().generate(collection_id, kind, topic), self.generated)

    def generated(self, artifact) -> None:
        if artifact is None: QMessageBox.information(self, "证据不足", "知识库中未找到足够依据。"); return
        self.refresh()

    def show_artifact(self, current, _previous) -> None:
        if current is None: return
        artifact = current.data(256); self.content.setMarkdown(artifact.content)
        citations = self.runtime.artifacts.list_citations(artifact.id)
        self.details_requested.emit("\n".join(f"[{c.display_index}] {c.source_title}\n{c.source_uri}" for c in citations))

    def delete(self) -> None:
        item = self.items.currentItem()
        if item is None or QMessageBox.question(self, "确认删除", "确认删除该学习产物？") != QMessageBox.StandardButton.Yes: return
        self.runtime.artifacts.delete(item.data(256).id); self.refresh()
