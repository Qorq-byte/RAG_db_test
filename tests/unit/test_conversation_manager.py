import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ragdb.desktop.chat_page import ChatPage
from ragdb.desktop.conversation_manager import ConversationManagerDialog
from ragdb.domain.models import Collection, Conversation, ConversationMessage
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteCollectionRepository, SQLiteConversationRepository


APP = QApplication.instance() or QApplication([])


@pytest.fixture
def saved(tmp_path):
    database = SQLiteDatabase(tmp_path / "chat.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="会话管理"))
    repo = SQLiteConversationRepository(database)
    sessions = []
    for index in range(3):
        session = repo.create(Conversation(collection_id=collection.id, title=f"问题 {index}", provider="test", model="test"))
        repo.record_turn(
            ConversationMessage(conversation_id=session.id, sequence=0, role="user", content=f"问题 {index}"),
            ConversationMessage(conversation_id=session.id, sequence=1, role="assistant", content=f"回答 {index}"), [],
        )
        sessions.append(session)
    return SimpleNamespace(collection=collection, repo=repo, sessions=sessions)


def checked(dialog, ids):
    for index in range(dialog.sessions.count()):
        item = dialog.sessions.item(index)
        if item.data(Qt.ItemDataRole.UserRole) in ids:
            item.setCheckState(Qt.CheckState.Checked)


def test_manager_selection_and_cancel_do_not_delete(saved, monkeypatch):
    dialog = ConversationManagerDialog(saved.repo, saved.collection.id, saved.sessions[0].id)
    assert dialog.sessions.count() == 3
    assert not dialog.delete_button.isEnabled()
    dialog.select_all.click()
    assert len(dialog.selected_items()) == 3
    dialog.clear_selection.click()
    assert not dialog.selected_items()
    checked(dialog, [saved.sessions[1].id])
    assert dialog.delete_button.text() == "删除所选（1）"
    def cancel(prompt):
        assert prompt.defaultButton() == prompt.button(QMessageBox.StandardButton.Cancel)
        assert "问题 1" in prompt.informativeText()
        return QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox, "exec", cancel)
    dialog.delete_button.click()
    assert len(saved.repo.list_for_collection(saved.collection.id)) == 3
    assert len(dialog.selected_items()) == 1
    dialog.close()


def test_manager_deletes_only_checked_and_emits_selected_ids(saved, monkeypatch):
    dialog = ConversationManagerDialog(saved.repo, saved.collection.id)
    selected = {saved.sessions[0].id, saved.sessions[2].id}
    checked(dialog, selected)
    seen = []
    dialog.conversations_deleted.connect(lambda collection, ids: seen.append((collection, set(ids))))
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    dialog.delete_button.click()
    assert seen == [(saved.collection.id, selected)]
    assert [item.id for item in saved.repo.list_for_collection(saved.collection.id)] == [saved.sessions[1].id]
    assert dialog.sessions.count() == 1
    assert not dialog.delete_button.isEnabled()
    assert "已删除 2 条" in dialog.feedback.text()
    dialog.close()


def test_manager_failure_preserves_selection(saved, monkeypatch):
    dialog = ConversationManagerDialog(saved.repo, saved.collection.id)
    checked(dialog, [saved.sessions[0].id])
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    def fail(*args):
        raise OSError("private database path")
    monkeypatch.setattr(saved.repo, "delete_many", fail)
    dialog.delete_button.click()
    assert "删除失败" in dialog.feedback.text()
    assert "private" not in dialog.feedback.text()
    assert len(dialog.selected_items()) == 1
    assert len(saved.repo.list_for_collection(saved.collection.id)) == 3
    dialog.close()


def test_empty_manager_and_read_failure(saved, monkeypatch):
    saved.repo.delete_many(saved.collection.id, [item.id for item in saved.sessions])
    dialog = ConversationManagerDialog(saved.repo, saved.collection.id)
    assert "暂无" in dialog.feedback.text()
    assert not dialog.delete_button.isEnabled()
    assert not dialog.select_all.isEnabled()
    def fail(*args, **kwargs):
        raise OSError("unreadable")
    monkeypatch.setattr(saved.repo, "list_for_collection", fail)
    assert not dialog.reload()
    assert "读取会话失败" in dialog.feedback.text()
    dialog.close()


def test_manager_includes_old_history_and_can_delete_all_selected(saved, monkeypatch):
    for index in range(22):
        saved.repo.create(Conversation(collection_id=saved.collection.id, title=f"更多会话 {index}", provider="test", model="test"))
    dialog = ConversationManagerDialog(saved.repo, saved.collection.id)
    assert dialog.sessions.count() == 25
    checked(dialog, [saved.sessions[0].id])
    assert len(dialog.selected_items()) == 1
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    dialog.delete_button.click()
    assert saved.repo.get(saved.sessions[0].id) is None
    assert dialog.sessions.count() == 24
    dialog.select_all.click()
    dialog.delete_button.click()
    assert dialog.sessions.count() == 0
    assert not dialog.delete_button.isEnabled()
    assert not dialog.select_all.isEnabled()
    assert saved.repo.list_for_collection(saved.collection.id, limit=None) == []
    dialog.close()


@pytest.mark.parametrize("delete_current", [False, True])
def test_chat_management_button_preserves_or_clears_active_conversation(saved, monkeypatch, delete_current):
    page = ChatPage(SimpleNamespace(conversations=saved.repo))
    assert not page.manage_sessions.isEnabled()
    page.set_collection(saved.collection.id, "会话管理", 1)
    page.session_id = saved.sessions[0].id
    page.refresh_sessions()
    page.select_session(page.sessions.currentIndex())
    page.question.setPlainText("未发送的草稿")
    details = []
    page.details_requested.connect(details.append)
    selected = saved.sessions[0 if delete_current else 1].id
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    def manage(dialog):
        checked(dialog, [selected])
        dialog.delete_button.click()
        return 0
    monkeypatch.setattr(ConversationManagerDialog, "exec", manage)
    page.manage_sessions.click()
    assert saved.repo.get(selected) is None
    assert page.question.toPlainText() == "未发送的草稿"
    if delete_current:
        assert page.session_id is None
        assert page.sessions.currentData() is None
        assert not page.transcript.messages
        assert details == [""]
    else:
        assert page.session_id == saved.sessions[0].id
        assert "回答 0" in page.transcript.toPlainText()
        assert details == []
    page.close()
