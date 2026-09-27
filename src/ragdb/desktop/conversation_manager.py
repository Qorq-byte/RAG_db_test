"""Choose saved conversations to delete without changing the active chat layout."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout,
)


class ConversationManagerDialog(QDialog):
    conversations_deleted = Signal(object, object)

    def __init__(self, repository, collection_id, current_session_id=None, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.collection_id = collection_id
        self.current_session_id = current_session_id
        self.setWindowTitle("管理会话")
        self.resize(600, 480)
        layout = QVBoxLayout(self)
        hint = QLabel("勾选要删除的会话。会话中的消息和引用会一起删除，知识库资料保留。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.sessions = QListWidget()
        self.sessions.setAccessibleName("选择要删除的会话")
        self.sessions.setWordWrap(True)
        self.sessions.setStyleSheet(
            "QListWidget::indicator { width: 14px; height: 14px; }"
            "QListWidget::indicator:unchecked { border: 1px solid palette(text); border-radius: 3px; }"
        )
        self.sessions.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.sessions, 1)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.feedback)
        actions = QHBoxLayout()
        self.select_all = QPushButton("全选")
        self.clear_selection = QPushButton("取消全选")
        self.delete_button = QPushButton("删除所选（0）")
        self.delete_button.setProperty("danger", True)
        close = QPushButton("关闭")
        for button in (self.select_all, self.clear_selection, self.delete_button, close):
            button.setAutoDefault(False)
            actions.addWidget(button)
        close.setDefault(True)
        layout.addLayout(actions)
        self.select_all.clicked.connect(lambda: self._check_all(Qt.CheckState.Checked))
        self.clear_selection.clicked.connect(lambda: self._check_all(Qt.CheckState.Unchecked))
        self.delete_button.clicked.connect(self.delete_selected)
        close.clicked.connect(self.reject)
        self.reload()

    def reload(self):
        try:
            conversations = self.repository.list_for_collection(self.collection_id, limit=None)
        except Exception:
            self.feedback.setText("读取会话失败，请关闭后重试。")
            self.delete_button.setEnabled(False)
            return False
        self.sessions.clear()
        for conversation in conversations:
            title = conversation.title or "未命名会话"
            current = "（当前会话）" if conversation.id == self.current_session_id else ""
            stamp = conversation.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{title}{current}\n{stamp} · {str(conversation.id)[:8]}")
            item.setData(Qt.ItemDataRole.UserRole, conversation.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.sessions.addItem(item)
        self._selection_changed()
        return True

    def selected_items(self):
        return [self.sessions.item(i) for i in range(self.sessions.count())
                if self.sessions.item(i).checkState() == Qt.CheckState.Checked]

    def _check_all(self, state):
        self.sessions.blockSignals(True)
        for index in range(self.sessions.count()):
            self.sessions.item(index).setCheckState(state)
        self.sessions.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self, *_args):
        count = len(self.selected_items())
        self.delete_button.setText(f"删除所选（{count}）")
        self.delete_button.setEnabled(count > 0)
        self.select_all.setEnabled(self.sessions.count() > 0)
        self.clear_selection.setEnabled(count > 0)
        self.feedback.setText(
            f"共 {self.sessions.count()} 条会话，已选 {count} 条" if self.sessions.count()
            else "当前集合暂无已保存的会话。"
        )

    def delete_selected(self):
        selected = self.selected_items()
        if not selected:
            return
        ids = tuple(item.data(Qt.ItemDataRole.UserRole) for item in selected)
        titles = "\n".join(f"• {item.data(Qt.ItemDataRole.UserRole + 1)[:80]}" for item in selected[:5])
        if len(selected) > 5:
            titles += f"\n…另有 {len(selected) - 5} 条"
        prompt = QMessageBox(self)
        prompt.setWindowTitle("确认删除会话")
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setTextFormat(Qt.TextFormat.PlainText)
        prompt.setText(f"删除所选的 {len(ids)} 条会话？")
        prompt.setInformativeText(f"{titles}\n\n相关消息和引用将一起删除，此操作无法撤销。知识库资料保留。")
        prompt.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(QMessageBox.StandardButton.Cancel)
        prompt.button(QMessageBox.StandardButton.Yes).setText("删除")
        prompt.button(QMessageBox.StandardButton.Cancel).setText("取消")
        if prompt.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.repository.delete_many(self.collection_id, ids)
        except Exception:
            self.feedback.setText("删除失败，所选会话未删除。请检查数据库是否可写后重试。")
            return
        self.conversations_deleted.emit(self.collection_id, ids)
        if self.current_session_id in ids:
            self.current_session_id = None
        if self.reload():
            self.feedback.setText(f"已删除 {count} 条会话，剩余 {self.sessions.count()} 条。")
