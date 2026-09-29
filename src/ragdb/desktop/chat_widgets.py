"""Native conversation widgets with safe text rendering and scroll following."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QTextDocument, QTextOption
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)


class QuestionEditor(QTextEdit):
    returnPressed = Signal()

    def __init__(self):
        super().__init__()
        self._composing = False
        self.setAcceptRichText(False)
        self.setFixedHeight(92)
        self.setAccessibleName("输入问题，Enter发送，Shift+Enter换行")

    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._composing:
                super().keyPressEvent(event)
            else:
                self.returnPressed.emit()
                event.accept()
            return
        super().keyPressEvent(event)

    def text(self):
        return self.toPlainText()

    def setText(self, text):
        self.setPlainText(text)


class MessageText(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setObjectName("chatMessageText")
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_height)

    def loadResource(self, resource_type, name):
        # Model output must never load file:// or remote images/resources.
        return None

    def fit_height(self, *_):
        self.setFixedHeight(max(34, int(self.document().size().height()) + 14))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(max(40, self.viewport().width()))
        self.fit_height()


class MessageBubble(QFrame):
    citations_requested = Signal(str)

    def __init__(self, role, content=""):
        super().__init__()
        self.role, self.content = role, content
        self.setObjectName("chatUserBubble" if role == "user" else "chatAssistantBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)
        self.caption = QLabel("你" if role == "user" else "RAGDB")
        self.caption.setProperty("muted", True)
        self.caption.setVisible(role != "user")
        layout.addWidget(self.caption)
        self.body = MessageText()
        if role == "user":
            self.body.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.body.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.body.document().setDefaultTextOption(
                QTextOption(Qt.AlignmentFlag.AlignLeft)
            )
        layout.addWidget(self.body)
        self.state = QLabel()
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        self.state.setProperty("muted", True)
        self.state.setVisible(role != "user")
        layout.addWidget(self.state)
        actions = QHBoxLayout()
        self.copy_button = QPushButton("复制回答")
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.content))
        self.references = QPushButton("查看引用")
        self.references.hide()
        self.references.clicked.connect(lambda: self.citations_requested.emit(self._citations))
        self.retry = QPushButton("重试")
        self.retry.hide()
        self.fallback = QPushButton("非流式重试")
        self.fallback.hide()
        for button in (self.copy_button, self.references, self.retry, self.fallback):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.copy_button.setVisible(role != "user")
        self._citations = ""
        self.set_content(content)

    def set_content(self, content):
        self.content = content
        if self.role == "user":
            self.body.setPlainText(content)
        else:
            self.body.document().setMarkdown(content, QTextDocument.MarkdownFeature.MarkdownNoHTML)
        self.body.fit_height()
        self.copy_button.setEnabled(bool(content))

    def fit_user_width(self, available_width: int):
        """Keep the right edge fixed while text grows up to a readable limit."""
        if self.role != "user":
            return
        margins = self.layout().contentsMargins()
        padding = margins.left() + margins.right() + 12
        metrics = QFontMetrics(self.body.font())
        natural = max((metrics.horizontalAdvance(line) for line in self.content.splitlines()), default=0)
        maximum = max(96, int(available_width * .72))
        self.setFixedWidth(min(maximum, max(72, natural + padding)))
        self.body.document().setTextWidth(max(40, self.width() - padding))
        self.body.fit_height()

    def set_citations(self, citations):
        self._citations = "\n\n".join(f"[{c.display_index}] {c.source_title}\n{c.source_uri}" for c in citations)
        self.references.setVisible(bool(citations))
        self.references.setText(f"查看 {len(citations)} 条引用")


class ConversationView(QScrollArea):
    following_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("conversationView")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(12, 20, 12, 24)
        self.layout.setSpacing(18)
        self.layout.addStretch()
        self.setWidget(self.container)
        self.messages = []
        self.following = True
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.verticalScrollBar().valueChanged.connect(self._value_changed)
        self.empty = QLabel("从一个问题开始\n回答将依据当前知识集合，附上可核验的来源。")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("muted", True)
        self.layout.insertWidget(0, self.empty)

    def add_message(self, role, text=""):
        self.empty.hide()
        bubble = MessageBubble(role, text)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble, 9)
            row_layout.addStretch(1)
        self.layout.insertWidget(self.layout.count() - 1, row)
        self.messages.append(bubble)
        bubble.fit_user_width(self.viewport().width() - 24)
        return bubble

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available = self.viewport().width() - 24
        for bubble in self.messages:
            bubble.fit_user_width(available)

    def clear(self):
        for bubble in self.messages:
            row = bubble.parentWidget()
            self.layout.removeWidget(row)
            row.deleteLater()
        self.messages.clear()
        self.empty.show()
        self.following = True

    def _range_changed(self, *_):
        if self.following:
            self.jump_to_latest()

    def _value_changed(self, value):
        self.following = self.verticalScrollBar().maximum() - value < 28
        self.following_changed.emit(self.following)

    def jump_to_latest(self):
        self.following = True
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
        self.following_changed.emit(True)

    def toPlainText(self):
        return "\n\n".join(bubble.content for bubble in self.messages)
