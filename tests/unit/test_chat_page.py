import os
import time
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ragdb.application.chat import AnswerService
from ragdb.desktop.chat_page import ChatPage
from ragdb.desktop.chat_widgets import MessageBubble, QuestionEditor
from ragdb.domain.models import Collection, SearchHit
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteCollectionRepository, SQLiteConversationRepository
from ragdb.infrastructure.chat.streaming import StreamingUnsupported


APP = QApplication.instance() or QApplication([])


def until(predicate):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(.005)
    APP.processEvents()
    assert predicate()


@pytest.fixture
def chat(tmp_path):
    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="demo"))
    repo = SQLiteConversationRepository(database)
    ready, release = Event(), Event()
    class Model:
        provider_name = "fake"
        model_name = "fake"
        def stream(self, messages, **kwargs):
            yield "第一段"
            ready.set()
            assert release.wait(6)
            yield "，第二段 [1]"
    model = Model()
    hit = SearchHit(rank=1, chunk_id="a", source_id=uuid4(), source_title="来源", source_uri="manual://sample",
                    source_generation=1, text="资料内容", routes=("hybrid",))
    search = SimpleNamespace(search=lambda *args: [hit])
    service = AnswerService(search, model, repo, evidence_limit=6, evidence_character_budget=1000, history_character_budget=500)
    runtime = SimpleNamespace(conversations=repo, answer_service=lambda: service)
    page = ChatPage(runtime)
    page.resize(850, 700)
    page.set_collection(collection.id, "demo", 1)
    page.show()
    yield SimpleNamespace(page=page, repo=repo, collection=collection, release=release, ready=ready, service=service)
    release.set()
    if page.busy:
        page.cancel()
        until(lambda: not page.busy)
    page.close()


def test_immediate_question_stream_progress_and_history_citations(chat):
    page = chat.page
    page.question.setPlainText("<b>用户问题</b>")
    page.ask()
    assert page.transcript.messages[0].body.toPlainText() == "<b>用户问题</b>"
    assert not page.sessions.isEnabled() and not page.new.isEnabled()
    assert not page.manage_sessions.isEnabled()
    assert not page.switch_collection.isEnabled()
    switches = []
    page.collection_switch_requested.connect(lambda: switches.append(True))
    page.request_collection_switch()
    assert switches == []
    page.manage_conversations()  # Direct calls are also blocked while generating.
    assert page.ask_button.text() == "停止生成"
    until(lambda: "第一段" in page.transcript.toPlainText())
    assert page.busy
    assert "正在生成" in page.transcript.messages[-1].state.text()
    assert not chat.repo.list_for_collection(chat.collection.id)
    page.ask()  # Duplicate input never adds another request/message.
    assert len(page.transcript.messages) == 2
    chat.release.set()
    until(lambda: not page.busy)
    assert page.transcript.messages[-1].content == "第一段，第二段 [1]"
    assert len(chat.repo.list_messages(page.session_id)) == 2
    assert page.manage_sessions.isEnabled()
    assert page.switch_collection.isEnabled()
    page.select_session(page.sessions.currentIndex())
    until(lambda: page.transcript.messages[-1].references.isVisible())
    evidence = []
    page.details_requested.connect(evidence.append)
    page.transcript.messages[-1].references.click()
    assert "manual://sample" in evidence[0]


def test_stop_preserves_partial_and_retry_creates_only_one_turn(chat):
    page = chat.page
    page.question.setPlainText("question")
    page.ask()
    until(lambda: "第一段" in page.transcript.toPlainText())
    page.cancel()
    chat.release.set()
    until(lambda: not page.busy)
    bubble = page.transcript.messages[-1]
    assert "未保存" in bubble.state.text()
    assert bubble.content == "第一段"
    assert not chat.repo.list_for_collection(chat.collection.id)
    bubble.retry.click()
    until(lambda: not page.busy)
    assert len(page.transcript.messages) == 2
    assert len(chat.repo.list_messages(page.session_id)) == 2


def test_context_change_cancels_old_request_without_cross_talk(chat):
    page = chat.page
    page.question.setPlainText("question")
    page.ask()
    until(lambda: chat.ready.is_set())
    next_collection = uuid4()
    old_token = page._token
    page.set_collection(next_collection, "next", 2)
    assert page.collection_label.text() == "当前提问集合：demo"
    assert not page.switch_collection.isEnabled()
    chat.release.set()
    until(lambda: not page.busy)
    assert page.collection_id == next_collection
    assert page.collection_label.text() == "当前提问集合：next"
    assert len(page.transcript.messages) == 2
    assert "未保存" in page.transcript.messages[-1].state.text()
    page._progress(old_token, "delta", "stale")
    assert "stale" not in page.transcript.toPlainText()


def test_switching_collection_keeps_session_and_continues_saved_history(chat):
    second = SQLiteCollectionRepository(chat.repo.database).create(Collection(name="第二个集合"))
    page = chat.page
    chat.release.set()
    page.question.setPlainText("第一轮问题")
    page.ask()
    until(lambda: not page.busy)
    session_id = page.session_id
    first_bubbles = list(page.transcript.messages)
    page.question.setPlainText("第二轮问题")
    page.set_collection(second.id, second.name, 2)
    assert page.session_id == session_id
    assert page.sessions.currentData() == session_id
    assert page.transcript.messages == first_bubbles
    assert page.question.toPlainText() == "第二轮问题"
    page.ask()
    until(lambda: not page.busy)
    assert page.session_id == session_id
    assert len(chat.repo.list_messages(session_id)) == 4
    assert len(page.transcript.messages) == 4
    assert len(chat.repo.list_for_collection(chat.collection.id)) == 1
    assert chat.repo.list_for_collection(second.id) == []
    restored = ChatPage(page.runtime)
    restored.set_collection(chat.collection.id, chat.collection.name, 1)
    index = next(i for i in range(restored.sessions.count()) if restored.sessions.itemData(i) == session_id)
    restored.sessions.setCurrentIndex(index)
    assert len(restored.transcript.messages) == 4
    assert restored.transcript.messages[-1].references.isHidden() is False
    restored.set_collection(second.id, second.name, 2)
    assert restored.session_id == session_id
    assert len(restored.transcript.messages) == 4
    restored.new_session()
    assert restored.session_id is None
    assert not restored.transcript.messages
    restored.close()


def test_retry_after_collection_switch_uses_current_scope_in_same_session(chat, monkeypatch):
    second = SQLiteCollectionRepository(chat.repo.database).create(Collection(name="重试集合"))
    page = chat.page
    chat.release.set()
    page.question.setPlainText("第一轮")
    page.ask()
    until(lambda: not page.busy)
    original_session = page.session_id
    original_ask = chat.service.ask
    calls = []
    failing = True
    def ask(collection_id, *args, **kwargs):
        calls.append(collection_id)
        if failing:
            raise RuntimeError("暂时失败")
        return original_ask(collection_id, *args, **kwargs)
    monkeypatch.setattr(chat.service, "ask", ask)
    page.question.setPlainText("需要重试的第二轮")
    page.ask()
    until(lambda: not page.busy)
    bubble = page.transcript.messages[-1]
    page.set_collection(second.id, second.name, 2)
    failing = False
    bubble.retry.click()
    until(lambda: not page.busy)
    assert calls == [chat.collection.id, second.id]
    assert page.session_id == original_session
    assert len(chat.repo.list_messages(original_session)) == 4
    assert len(page.transcript.messages) == 4


def test_only_explicit_session_selection_replaces_display(chat):
    second = SQLiteCollectionRepository(chat.repo.database).create(Collection(name="其他会话集合"))
    page = chat.page
    chat.release.set()
    page.question.setPlainText("当前会话问题")
    page.ask()
    until(lambda: not page.busy)
    first_session = page.session_id
    other = chat.service.ask(second.id, "另一条会话的问题", stream=True).conversation
    page.set_collection(second.id, second.name, 2)
    assert page.session_id == first_session
    assert "当前会话问题" in page.transcript.toPlainText()
    index = next(i for i in range(page.sessions.count()) if page.sessions.itemData(i) == other.id)
    page.sessions.setCurrentIndex(index)
    assert page.session_id == other.id
    assert "另一条会话的问题" in page.transcript.toPlainText()
    assert "当前会话问题" not in page.transcript.toPlainText()
    assert len(chat.repo.list_messages(first_session)) == 2


def test_explicit_stream_rejection_offers_manual_fallback(chat, monkeypatch):
    calls = []
    original = chat.service.ask
    def ask(*args, **kwargs):
        calls.append(kwargs['stream'])
        if kwargs['stream']:
            raise StreamingUnsupported()
        kwargs['stream'] = True  # Use fixture's synthetic stream to complete fallback request.
        return original(*args, **kwargs)
    monkeypatch.setattr(chat.service, "ask", ask)
    chat.release.set()
    page = chat.page
    page.question.setPlainText("question")
    page.ask()
    until(lambda: not page.busy)
    assert calls == [True]
    page.transcript.messages[-1].fallback.click()
    until(lambda: not page.busy)
    assert calls == [True, False]
    assert page.session_id


def test_multiline_editor_enter_and_ime():
    editor = QuestionEditor()
    editor.show()
    sends = []
    editor.returnPressed.connect(lambda: sends.append(True))
    editor.setPlainText("first")
    QTest.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert "\n" in editor.toPlainText()
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert sends == [True]
    APP.sendEvent(editor, QInputMethodEvent("pin", []))
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert sends == [True]
    editor.close()


def test_safe_markdown_and_copy():
    bubble = MessageBubble("assistant", "**粗体**\n\n```python\nprint('hello')\n```\n<script>bad()</script>\n![x](file:///private.txt)")
    assert "print('hello')" in bubble.body.toPlainText()
    assert bubble.body.loadResource(2, "file:///private.txt") is None
    assert not bubble.body.openLinks()
    bubble.copy_button.click()
    assert APP.clipboard().text() == bubble.content


def test_scrolling_up_is_not_overridden_by_new_content(chat):
    page = chat.page
    for _ in range(10):
        page._add_bubble("assistant", "长回答\n\n" * 8)
    until(lambda: page.transcript.verticalScrollBar().maximum() > 300)
    bar = page.transcript.verticalScrollBar()
    bar.setValue(0)
    assert not page.transcript.following
    page.transcript.messages[-1].set_content("继续生成\n\n" * 30)
    APP.processEvents()
    assert bar.value() == 0
    page.latest.click()
    assert bar.value() == bar.maximum()
