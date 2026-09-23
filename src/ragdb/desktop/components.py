"""Reusable visual components for the desktop workbench."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class StatCard(QFrame):
    def __init__(self, label: str, value: str = "—") -> None:
        super().__init__()
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        caption = QLabel(label)
        caption.setProperty("muted", True)
        self.value = QLabel(value)
        self.value.setStyleSheet("font-size: 26px; font-weight: 650;")
        layout.addWidget(caption)
        layout.addWidget(self.value)


class StatusBadge(QLabel):
    def __init__(self, text: str, status: str = "success") -> None:
        super().__init__(text)
        self.setProperty("status", status)


class ResultCard(QFrame):
    """Compact evidence preview used by search results."""

    def __init__(self, title: str, snippet: str, metadata: str = "") -> None:
        super().__init__()
        self.setProperty("resultCard", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setProperty("resultTitle", True)
        body = QLabel(snippet)
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        if metadata:
            meta = QLabel(metadata)
            meta.setProperty("muted", True)
            layout.addWidget(meta)


class EmptyState(QWidget):
    action_requested = Signal()

    def __init__(self, title: str, description: str, action: str | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 17px; font-weight: 600;")
        detail = QLabel(description)
        detail.setProperty("muted", True)
        detail.setWordWrap(True)
        layout.addStretch()
        layout.addWidget(heading)
        layout.addWidget(detail)
        if action:
            button = QPushButton(action)
            button.setProperty("primary", True)
            button.clicked.connect(self.action_requested)
            layout.addWidget(button)
        layout.addStretch()


class PageShell(QWidget):
    def __init__(self, title: str, description: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        header = QHBoxLayout()
        labels = QVBoxLayout()
        heading = QLabel(title)
        heading.setProperty("pageTitle", True)
        labels.addWidget(heading)
        if description:
            subtitle = QLabel(description)
            subtitle.setProperty("muted", True)
            labels.addWidget(subtitle)
        header.addLayout(labels)
        header.addStretch()
        self.actions = QHBoxLayout()
        header.addLayout(self.actions)
        layout.addLayout(header)
        self.states = QStackedWidget()
        layout.addWidget(self.states, 1)

    def set_content(self, widget: QWidget) -> None:
        self.states.addWidget(widget)
        self.states.setCurrentWidget(widget)

    def show_message(self, title: str, description: str) -> None:
        state = EmptyState(title, description)
        self.states.addWidget(state)
        self.states.setCurrentWidget(state)


class DetailPanel(QWidget):
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("detailPanel")
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel("详情")
        self.title.setStyleSheet("font-weight: 650;")
        close = QPushButton("×")
        close.setFixedWidth(32)
        close.clicked.connect(self.hide)
        close.clicked.connect(self.closed)
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(close)
        layout.addLayout(header)
        self.content = QTextBrowser()
        self.content.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.content)

    def show_text(self, text: str, title: str = "详情") -> None:
        self.title.setText(title)
        self.content.setPlainText(text)
        self.show()
