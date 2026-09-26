"""Accessible native sun / moon / monitor theme selector."""

import math
from PySide6.QtCore import QEvent, QLineF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

from ragdb.desktop.theme import ThemeMode, DARK, LIGHT


def theme_icon(mode, color):
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if mode is ThemeMode.LIGHT:
        painter.drawEllipse(QRectF(8, 8, 8, 8))
        for i in range(8):
            angle = i * math.pi / 4
            painter.drawLine(QLineF(12 + 7 * math.cos(angle), 12 + 7 * math.sin(angle),
                                   12 + 10 * math.cos(angle), 12 + 10 * math.sin(angle)))
    elif mode is ThemeMode.DARK:
        path, cut = QPainterPath(), QPainterPath()
        path.addEllipse(QRectF(4, 3, 17, 17))
        cut.addEllipse(QRectF(10, 0, 15, 15))
        painter.drawPath(path.subtracted(cut))
    else:
        painter.drawRoundedRect(QRectF(3, 4, 18, 13), 2, 2)
        painter.drawLine(12, 17, 12, 21)
        painter.drawLine(8, 21, 16, 21)
    painter.end()
    return QIcon(pixmap)


class ThemeSwitcher(QWidget):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setAccessibleName("界面主题")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for mode, label in ((ThemeMode.LIGHT, "浅色"), (ThemeMode.DARK, "深色"), (ThemeMode.SYSTEM, "跟随系统")):
            button = QToolButton(self)
            button.setProperty("themeIcon", True)
            button.setCheckable(True)
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(22, 22))
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, selected=mode: manager.set_mode(selected))
            self.group.addButton(button)
            self.buttons[mode] = button
            button.installEventFilter(self)
            layout.addWidget(button)
        manager.changed.connect(self._sync)
        self._sync()

    def _sync(self, *_):
        colors = DARK if self.manager.resolved_mode() is ThemeMode.DARK else LIGHT
        for mode, button in self.buttons.items():
            selected = self.manager.mode is mode
            button.setChecked(selected)
            button.setIcon(theme_icon(mode, "#ffffff" if selected or button.property("wetNear") else colors["text"]))
            button.setAccessibleDescription("当前主题" if selected else "切换界面主题")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.DynamicPropertyChange and event.propertyName() == b"wetNear":
            self._sync()
        return False
