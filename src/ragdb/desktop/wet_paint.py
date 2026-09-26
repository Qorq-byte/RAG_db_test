"""Pointer-proximity wet paint for native buttons, without changing hit targets."""

import math
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit, QTextEdit, QWidget, QPushButton, QToolButton
from shiboken6 import isValid


DRIPS = ((.10, 24, .5), (.30, 20, 3), (.57, 10, 4.25), (.85, 16, 1.5))


class PaintOverlay(QWidget):
    def __init__(self, window, controller):
        super().__init__(window)
        self.controller = controller
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event):
        control = self.controller
        button = control.active_button
        if not button or not isValid(button) or not control.timer.isActive():
            return
        point = self.mapFromGlobal(button.mapToGlobal(QPoint()))
        rect = QRectF(point.x(), point.y(), button.width(), button.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Liquid can extend beyond its button, but never obscure another control
        # or a text label. The overlay itself never receives mouse input.
        region = QRegion(self.rect())
        for widget in self.parentWidget().findChildren(QWidget):
            if (widget is self or widget is button or not widget.isVisible()
                    or button.isAncestorOf(widget)):
                continue
            if isinstance(widget, (QAbstractButton, QLabel, QLineEdit, QTextEdit, QComboBox)):
                p = self.mapFromGlobal(widget.mapToGlobal(QPoint()))
                region -= QRegion(QRect(p, widget.size()))
        painter.setClipRegion(region)
        color = QColor("#be123c" if button.property("danger") else "#4f46e5")
        painter.setPen(Qt.PenStyle.NoPen)
        elapsed = monotonic() - control.started
        reveal = min(1, elapsed / .15)
        for left, height, delay in DRIPS:
            # Match the reference: 2s elastic length cycle, 2s pause, staggered
            # falling droplets. No liquid is painted outside proximity mode.
            phase = max(0, elapsed - delay) % 4
            if phase < .5:
                scale = .75 + .25 * (phase / .5) ** 2
            elif phase < 2:
                scale = 1 - .25 * ((phase - .5) / 1.5) ** 2
            else:
                scale = .75
            length = height * scale * reveal
            x = rect.left() + left * rect.width()
            y = rect.bottom() - 1
            width = min(8, max(3, rect.width() * .07))
            painter.setOpacity(reveal)
            painter.setBrush(color)
            path = QPainterPath()
            path.moveTo(x - 5, y)
            path.cubicTo(x, y, x, y + 3, x, y + 6)
            path.lineTo(x, y + max(6, length - width / 2))
            path.quadTo(x + width / 2, y + length + width / 2, x + width, y + max(6, length - width / 2))
            path.lineTo(x + width, y + 6)
            path.cubicTo(x + width, y + 3, x + width, y, x + width + 5, y)
            path.closeSubpath()
            painter.drawPath(path)
            if elapsed >= delay and phase < 2:
                t = phase / 2
                painter.setOpacity((1 - t*t) * reveal)
                painter.drawEllipse(QRectF(x, y + length - 8 + 58 * t*t, width, width))


class WetPaintController(QObject):
    radius = 18

    def __init__(self, app):
        super().__init__(app)
        self.active_button = None
        self.overlay = None
        self.started = 0.0
        self.reduce_motion = False
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        app.installEventFilter(self)
        for widget in app.allWidgets():
            widget.setMouseTracking(True)

    def set_reduce_motion(self, enabled):
        self.reduce_motion = enabled
        if enabled:
            self.clear()

    def clear(self):
        button, self.active_button = self.active_button, None
        self.timer.stop()
        if button is not None and isValid(button):
            self._near_style(button, False)
        if self.overlay is not None and isValid(self.overlay):
            self.overlay.hide()

    @staticmethod
    def _near_style(button, enabled):
        button.setProperty("wetNear", enabled)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def pointer_moved(self, window, global_point):
        if self.reduce_motion or not window.isVisible():
            self.clear()
            return
        modal = QApplication.activeModalWidget()
        if modal is not None and modal.window() is not window:
            self.clear()
            return
        best, distance = None, float("inf")
        for button in window.findChildren(QAbstractButton):
            if (not isinstance(button, (QPushButton, QToolButton))
                    or not button.isVisible() or not button.isEnabled()
                    or button.property("wetPaintDisabled")):
                continue
            rect = QRect(button.mapToGlobal(QPoint()), button.size())
            dx = max(rect.left() - global_point.x(), 0, global_point.x() - rect.right())
            dy = max(rect.top() - global_point.y(), 0, global_point.y() - rect.bottom())
            current = math.hypot(dx, dy)
            if current <= self.radius and current < distance:
                # Exclude buttons clipped out of scroll areas.
                local = button.mapFromGlobal(global_point)
                closest = QPoint(max(0, min(button.width()-1, local.x())), max(0, min(button.height()-1, local.y())))
                if not button.visibleRegion().contains(closest):
                    continue
                best, distance = button, current
        if best is self.active_button:
            return
        self.clear()
        if best is None:
            return
        self.active_button = best
        self._near_style(best, True)
        if self.overlay is None or not isValid(self.overlay) or self.overlay.parentWidget() is not window:
            if self.overlay is not None and isValid(self.overlay):
                self.overlay.deleteLater()
            self.overlay = PaintOverlay(window, self)
        self.overlay.setGeometry(window.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.started = monotonic()
        self.timer.start()

    def _tick(self):
        button = self.active_button
        if (button is None or not isValid(button) or not button.isVisible()
                or not button.isEnabled() or self.reduce_motion):
            self.clear()
            return
        if self.overlay is not None and isValid(self.overlay):
            self.overlay.setGeometry(button.window().rect())
            self.overlay.raise_()
            self.overlay.update()

    def eventFilter(self, watched, event):
        kind = event.type()
        if isinstance(watched, QWidget) and not isinstance(watched, PaintOverlay):
            if kind == QEvent.Type.Show:
                watched.setMouseTracking(True)
            elif kind in (QEvent.Type.MouseMove, QEvent.Type.Enter) and hasattr(event, "globalPosition"):
                self.pointer_moved(watched.window(), event.globalPosition().toPoint())
            elif kind in (QEvent.Type.Hide, QEvent.Type.EnabledChange):
                if watched is self.active_button or (self.overlay is not None and isValid(self.overlay) and watched is self.overlay.parentWidget()):
                    self.clear()
            elif kind in (QEvent.Type.WindowDeactivate, QEvent.Type.Leave):
                if self.overlay is not None and isValid(self.overlay) and watched is self.overlay.parentWidget():
                    self.clear()
        if kind == QEvent.Type.ApplicationDeactivate:
            self.clear()
        return False


def install_wet_paint(app, reduce_motion=False):
    control = getattr(app, "_ragdb_wet_paint", None)
    if control is None:
        control = WetPaintController(app)
        app._ragdb_wet_paint = control
    control.set_reduce_motion(reduce_motion)
    return control
