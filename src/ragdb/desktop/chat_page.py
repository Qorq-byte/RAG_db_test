"""Conversation page: immediate messages, real progress and streamed answers."""

from threading import Event
from time import monotonic
from uuid import uuid4

from PySide6.QtCore import QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ragdb.desktop.components import PageShell
from ragdb.desktop.chat_widgets import ConversationView, QuestionEditor
from ragdb.desktop.conversation_manager import ConversationManagerDialog
from ragdb.desktop.workers import BackgroundTask
from ragdb.infrastructure.chat.streaming import StreamingUnsupported


class ChatPage(PageShell):
    details_requested = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, runtime):
        super().__init__("问答", "基于当前知识集合，边生成边呈现答案与依据。")
        self.runtime = runtime
        self.collection_id = self.session_id = None
        self.generation = 0
        self._task = None
        self._token = None
        self._cancel = Event()
        self._pending_context = None
        self._stage = ""
        self._buffer = ""
        self._bubble = None
        self._started = 0
        self.new = QPushButton("新会话")
        self.new.clicked.connect(self.new_session)
        self.actions.addWidget(self.new)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("会话"))
        self.sessions = QComboBox()
        self.sessions.setMinimumWidth(180)
        self.sessions.currentIndexChanged.connect(self.select_session)
        bar.addWidget(self.sessions, 1)
        self.manage_sessions = QPushButton("管理会话")
        self.manage_sessions.setEnabled(False)
        self.manage_sessions.clicked.connect(self.manage_conversations)
        bar.addWidget(self.manage_sessions)
        layout.addLayout(bar)
        self.transcript = ConversationView()
        layout.addWidget(self.transcript, 1)
        self.latest = QPushButton("回到最新回答 ↓")
        self.latest.hide()
        self.latest.clicked.connect(self.transcript.jump_to_latest)
        self.transcript.following_changed.connect(lambda following: self.latest.setVisible(not following))
        layout.addWidget(self.latest)
        composer = QFrame()
        composer.setProperty("card", True)
        form = QVBoxLayout(composer)
        self.question = QuestionEditor()
        self.question.setPlaceholderText("向当前知识集合提问…")
        self.question.returnPressed.connect(self.ask)
        form.addWidget(self.question)
        row = QHBoxLayout()
        self.feedback = QLabel("Enter 发送 · Shift+Enter 换行")
        self.feedback.setProperty("muted", True)
        row.addWidget(self.feedback, 1)
        self.ask_button = QPushButton("发送")
        self.ask_button.setProperty("primary", True)
        self.ask_button.clicked.connect(self.send_or_stop)
        row.addWidget(self.ask_button)
        form.addLayout(row)
        layout.addWidget(composer)
        self.set_content(content)
        self._timer = QTimer(self)
        self._timer.setInterval(75)
        self._timer.timeout.connect(self._flush)

    @property
    def busy(self):
        return self._task is not None

    @property
    def _task_in_flight(self):
        return self.busy

    def set_collection(self, collection_id, name, generation):
        if self.busy:
            self._pending_context = (collection_id, name, generation)
            self.cancel()
            return
        changed = collection_id != self.collection_id
        self.collection_id, self.generation = collection_id, generation
        self.manage_sessions.setEnabled(collection_id is not None)
        if changed:
            self.session_id = None
            self.transcript.clear()
        self.refresh_sessions()

    def refresh_sessions(self):
        self.sessions.blockSignals(True)
        self.sessions.clear()
        self.sessions.addItem("新会话", None)
        if self.collection_id:
            for session in self.runtime.conversations.list_for_collection(self.collection_id):
                self.sessions.addItem(session.title or str(session.id), session.id)
        if self.session_id:
            # QVariant compares opaque Python UUID objects by identity, while
            # repository reads create equal but distinct UUID instances.
            selected = next((i for i in range(self.sessions.count())
                             if self.sessions.itemData(i) == self.session_id), 0)
            self.sessions.setCurrentIndex(selected)
        self.sessions.blockSignals(False)

    def _add_bubble(self, role, text=""):
        bubble = self.transcript.add_message(role, text)
        bubble.citations_requested.connect(self.details_requested)
        return bubble

    def select_session(self, _index):
        if self.busy:
            return
        self.session_id = self.sessions.currentData()
        self.transcript.clear()
        if self.session_id:
            for message in self.runtime.conversations.list_messages(self.session_id):
                bubble = self._add_bubble(message.role.value, message.content)
                if message.role.value == "assistant":
                    bubble.set_citations(self.runtime.conversations.list_citations(message.id))

    def new_session(self):
        if self.busy:
            return
        self.session_id = None
        self.sessions.setCurrentIndex(0)
        self.transcript.clear()
        self.question.setFocus()

    def manage_conversations(self):
        if self.busy or self.collection_id is None:
            return
        dialog = ConversationManagerDialog(
            self.runtime.conversations, self.collection_id, self.session_id, self,
        )
        dialog.conversations_deleted.connect(self._conversations_deleted)
        dialog.exec()
        dialog.deleteLater()

    def _conversations_deleted(self, collection_id, session_ids):
        if collection_id != self.collection_id or self.busy:
            return
        if self.session_id in session_ids:
            self.generation += 1
            self.new_session()
            self._bubble = None
            self._buffer = ""
            self.details_requested.emit("")
            self.feedback.setText("当前会话已删除，可开始新会话")
        self.refresh_sessions()

    def send_or_stop(self):
        self.cancel() if self.busy else self.ask()

    def cancel(self):
        if self.busy:
            self._cancel.set()
            self._stage = "已请求停止，等待当前操作结束"
            self.ask_button.setEnabled(False)
            self._flush()

    def ask(self):
        if self.busy:
            return
        question = self.question.toPlainText().strip()
        if not self.collection_id:
            self.feedback.setText("请先选择知识集合")
            return
        if not question:
            return
        self.question.clear()
        self._add_bubble("user", question)
        bubble = self._add_bubble("assistant")
        context = (self.collection_id, self.session_id, self.generation)
        bubble.retry.clicked.connect(lambda: self._retry(question, bubble, context, True))
        bubble.fallback.clicked.connect(lambda: self._retry(question, bubble, context, False))
        self._start(question, bubble, context, True)

    def _retry(self, question, bubble, context, stream):
        if self.busy or context != (self.collection_id, self.session_id, self.generation):
            return
        self._start(question, bubble, context, stream)

    def _start(self, question, bubble, context, stream):
        self._cancel.clear()
        self._bubble = bubble
        self._buffer = ""
        self._stage = "正在准备检索"
        self._started = monotonic()
        self._token = uuid4()
        token = self._token
        collection_id, session_id, _ = context
        bubble.set_content("")
        bubble.retry.hide()
        bubble.fallback.hide()
        self.transcript.jump_to_latest()
        def run():
            service = self.runtime.answer_service()
            try:
                return service.ask(
                    collection_id, question, session_id, title=question[:60], stream=stream,
                    on_event=lambda kind, value: task.signals.progress.emit(token, kind, value),
                    should_cancel=self._cancel.is_set,
                )
            except StreamingUnsupported:
                task.signals.progress.emit(token, "unsupported", True)
                raise
            finally:
                if hasattr(service, "close"):
                    service.close()
        task = BackgroundTask(token, run)
        self._task = task
        task.signals.progress.connect(self._progress)
        task.signals.succeeded.connect(self._succeeded)
        task.signals.failed.connect(self._failed)
        task.signals.finished.connect(self._finished)
        self.sessions.setEnabled(False)
        self.manage_sessions.setEnabled(False)
        self.new.setEnabled(False)
        self.question.setEnabled(False)
        self.ask_button.setText("停止生成")
        self.ask_button.setEnabled(True)
        self.busy_changed.emit(True)
        self._timer.start()
        self._flush()
        QThreadPool.globalInstance().start(task)

    @Slot(object, str, object)
    def _progress(self, token, kind, value):
        if token != self._token:
            return
        if kind == "delta":
            self._buffer += value
        elif kind == "stage" and not self._cancel.is_set():
            self._stage = value
        elif kind == "unsupported":
            self._bubble.fallback.show()

    def _flush(self):
        if self._bubble is None:
            return
        if self._bubble.content != self._buffer:
            self._bubble.set_content(self._buffer)
        elapsed = int(monotonic() - self._started)
        self._bubble.state.setText(f"{self._stage} · {elapsed} 秒")

    @Slot(object, object)
    def _succeeded(self, token, answer):
        if token != self._token:
            return
        self._timer.stop()
        self.session_id = answer.conversation.id
        self._buffer = answer.content
        self._stage = "已完成"
        self._bubble.set_citations(answer.citations)
        self._flush()
        self.feedback.setText("回答已保存，可继续提问")
        for bubble in self.transcript.messages:
            bubble.retry.hide()
            bubble.fallback.hide()
        self.refresh_sessions()

    @Slot(object, str)
    def _failed(self, token, error):
        if token != self._token:
            return
        self._timer.stop()
        self._stage = "已停止 · 未保存" if self._cancel.is_set() else "生成失败 · 未保存"
        self._flush()
        self._bubble.state.setText(self._bubble.state.text() + "\n" + error)
        self._bubble.retry.show()
        self.feedback.setText("可在回答下重试，或输入新的问题")

    @Slot(object)
    def _finished(self, token):
        if token != self._token:
            return
        self._timer.stop()
        self._task = None
        self._token = None
        self.sessions.setEnabled(True)
        self.manage_sessions.setEnabled(self.collection_id is not None)
        self.new.setEnabled(True)
        self.question.setEnabled(True)
        self.ask_button.setEnabled(True)
        self.ask_button.setText("发送")
        self.busy_changed.emit(False)
        if self._pending_context:
            context, self._pending_context = self._pending_context, None
            self.set_collection(*context)
        self.question.setFocus()
