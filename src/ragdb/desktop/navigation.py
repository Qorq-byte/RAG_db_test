"""Animated sidebar and top bar for the desktop workbench."""

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ragdb.desktop.theme import ThemeManager, ThemeMode


NAV_GROUPS = (
    ("知识库", (("⌂", "概览", 0), ("▤", "集合与资料", 1), ("⌕", "检索", 2))),
    ("学习", (("◇", "问答", 3), ("☆", "学习产物", 4))),
    ("系统", (("⚙", "任务与诊断", 5),)),
)


class NavButton(QPushButton):
    hovered = Signal(object)

    def __init__(self, icon_text: str, label: str, page: int) -> None:
        super().__init__(f"{icon_text}   {label}")
        self.icon_text, self.label, self.page = icon_text, label, page
        self.setCheckable(True)
        self.setCursor(QtCursor.pointing())
        self.setToolTip(label)
        self.setFixedHeight(40)
        self.setProperty("navItem", True)

    def set_collapsed(self, collapsed: bool) -> None:
        self.setText(
            self.icon_text if collapsed else f"{self.icon_text}   {self.label}"
        )

    def enterEvent(self, event: QEnterEvent) -> None:
        self.hovered.emit(self)
        super().enterEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().highlight().color()
        painter.setPen(QPen(color, 2))
        for y, width in ((7, 13), (13, 17), (self.height() - 8, 13)):
            painter.drawLine(2, y, width, y)
        if self.isChecked():
            painter.drawLine(5, self.height() // 2, 27, self.height() // 2)


class QtCursor:
    @staticmethod
    def pointing():
        return Qt.CursorShape.PointingHandCursor

    @staticmethod
    def horizontal_resize():
        return Qt.CursorShape.SizeHorCursor

    @staticmethod
    def arrow():
        return Qt.CursorShape.ArrowCursor


class SidebarWidget(QWidget):
    page_selected = Signal(int)
    collapsed_changed = Signal(bool)
    user_collapsed_changed = Signal(bool)
    width_adjusted = Signal(int)

    def __init__(
        self,
        reduce_motion: bool = False,
        expanded_width: int = 236,
        collapsed: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self._collapsed = False
        self._expanded_width = self._clamp_width(expanded_width)
        self._resizing = False
        self._resize_origin_x = 0
        self._resize_origin_width = self._expanded_width
        self.reduce_motion = reduce_motion
        self.setMouseTracking(True)
        self.setToolTip("拖拽右侧边缘以调整导航栏宽度")
        self.set_sidebar_width(self._expanded_width)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(5)
        top = QHBoxLayout()
        self.brand = QLabel("RAG DB")
        self.brand.setStyleSheet(
            "font-size: 17px; font-weight: 700; letter-spacing: 1px;"
        )
        self.toggle = QToolButton()
        self.toggle.setText("‹")
        self.toggle.setToolTip("折叠导航")
        self.toggle.clicked.connect(self.toggle_collapsed)
        top.addWidget(self.brand)
        top.addStretch()
        top.addWidget(self.toggle)
        layout.addLayout(top)
        self.collection = QLabel("未选择集合")
        self.collection.setProperty("muted", True)
        layout.addWidget(self.collection)
        layout.addSpacing(12)
        self.group_labels, self.buttons = [], []
        for group, items in NAV_GROUPS:
            heading = QLabel(group.upper())
            heading.setProperty("navGroup", True)
            self.group_labels.append(heading)
            layout.addWidget(heading)
            for icon, label, page in items:
                button = NavButton(icon, label, page)
                button.clicked.connect(
                    lambda _checked=False, target=page: self.select_page(target)
                )
                button.hovered.connect(self.move_highlight)
                self.buttons.append(button)
                layout.addWidget(button)
            layout.addSpacing(8)
        layout.addStretch()
        self.highlight = QFrame(self)
        self.highlight.setObjectName("navHover")
        self.highlight.lower()
        self.highlight.hide()
        self.hover_animation = QPropertyAnimation(self.highlight, b"geometry", self)
        self.hover_animation.setDuration(170)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.width_animation = QPropertyAnimation(self, b"sidebarWidth", self)
        self.width_animation.setDuration(190)
        self.width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.select_page(0)
        if collapsed:
            self.set_collapsed(True)

    @staticmethod
    def _clamp_width(width: int) -> int:
        return max(160, min(400, width))

    def get_sidebar_width(self) -> int:
        return self.width()

    def set_sidebar_width(self, value: int) -> None:
        self.setMinimumWidth(value)
        self.setMaximumWidth(value)

    sidebarWidth = Property(int, get_sidebar_width, set_sidebar_width)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def select_page(self, page: int) -> None:
        for button in self.buttons:
            button.setChecked(button.page == page)
        self.page_selected.emit(page)

    def move_highlight(self, button: NavButton) -> None:
        point = button.mapTo(self, button.rect().topLeft())
        target = QRect(10, point.y(), self.width() - 20, button.height())
        self.highlight.show()
        if self.reduce_motion:
            self.highlight.setGeometry(target)
        else:
            self.hover_animation.stop()
            self.hover_animation.setStartValue(self.highlight.geometry())
            self.hover_animation.setEndValue(target)
            self.hover_animation.start()

    def toggle_collapsed(self) -> None:
        collapsed = not self._collapsed
        self.set_collapsed(collapsed)
        self.user_collapsed_changed.emit(collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        target = 68 if collapsed else self._expanded_width
        self.brand.setText("R" if collapsed else "RAG DB")
        self.collection.setVisible(not collapsed)
        self.toggle.setText("›" if collapsed else "‹")
        for label in self.group_labels:
            label.setVisible(not collapsed)
        for button in self.buttons:
            button.set_collapsed(collapsed)
        if self.reduce_motion:
            self.set_sidebar_width(target)
        else:
            self.width_animation.stop()
            self.width_animation.setStartValue(self.width())
            self.width_animation.setEndValue(target)
            self.width_animation.start()
        self.collapsed_changed.emit(collapsed)

    def set_expanded_width(self, width: int) -> None:
        self._expanded_width = self._clamp_width(width)
        if not self._collapsed:
            self.set_sidebar_width(self._expanded_width)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_resize_edge(event):
            self._resizing = True
            self._resize_origin_x = int(event.globalPosition().x())
            self._resize_origin_width = self._expanded_width
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resizing:
            width = self._resize_origin_width + int(event.globalPosition().x()) - self._resize_origin_x
            self.set_expanded_width(width)
            event.accept()
            return
        self.setCursor(
            QtCursor.horizontal_resize() if self._is_resize_edge(event) else QtCursor.arrow()
        )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._resizing and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = False
            self.width_adjusted.emit(self._expanded_width)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _is_resize_edge(self, event: QMouseEvent) -> bool:
        return not self._collapsed and event.position().x() >= self.width() - 10


class TopBar(QWidget):
    detail_toggled = Signal()

    def __init__(self, theme_manager: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("topBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 10, 8)
        self.title = QLabel("概览")
        self.title.setStyleSheet("font-size: 18px; font-weight: 650;")
        self.collection = QLabel("未选择集合")
        self.collection.setProperty("muted", True)
        self.task_status = QLabel("后台空闲")
        self.task_status.setProperty("muted", True)
        self.theme = QComboBox()
        self.theme.addItem("跟随系统", ThemeMode.SYSTEM)
        self.theme.addItem("浅色", ThemeMode.LIGHT)
        self.theme.addItem("深色", ThemeMode.DARK)
        self.theme.setCurrentIndex(max(0, self.theme.findData(theme_manager.mode)))
        self.theme.currentIndexChanged.connect(
            lambda _index: theme_manager.set_mode(self.theme.currentData())
        )
        detail = QToolButton()
        detail.setText("详情")
        detail.clicked.connect(self.detail_toggled)
        layout.addWidget(self.title)
        layout.addWidget(self.collection)
        layout.addStretch()
        layout.addWidget(self.task_status)
        layout.addWidget(self.theme)
        layout.addWidget(detail)

    def set_page(self, title: str) -> None:
        self.title.setText(title)

    def set_collection(self, _collection_id, name: str, _generation: int) -> None:
        self.collection.setText(name)
