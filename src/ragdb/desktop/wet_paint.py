"""Pointer-proximity wet paint for native buttons, without changing hit targets."""

import math
from time import monotonic

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit, QTextEdit, QWidget, QPushButton, QToolButton
from shiboken6 import isValid


DRIPS = ((.10, 24, .5), (.30, 20, 3), (.57, 10, 4.25), (.85, 16, 1.5))


# Framer Motion's easeIn is cubic-bezier(.42, 0, 1, 1), not t squared.
EASE_IN = QEasingCurve(QEasingCurve.Type.BezierSpline)
EASE_IN.addCubicBezierSegment(QPointF(.42, 0), QPointF(1, 1), QPointF(1, 1))


def drip_frame(elapsed, delay):
    """Reference parent scale and child translation/opacity (before transform)."""
    phase = max(0.0, elapsed - delay) % 4.0
    ease = EASE_IN.valueForProgress
    if phase <= .5:
        scale = .75 + .25 * ease(phase / .5)
    elif phase < 2:
        scale = 1 - .25 * ease((phase - .5) / 1.5)
    else:
        scale = .75
    fall = ease(min(1.0, phase / 2))
    return scale, -8 + 58 * fall, 1 - fall


def drip_outline(height):
    """8px round-bottom body plus the reference's 5.4px concave joins."""
    path = QPainterPath(QPointF(-5.4, 0))
    path.cubicTo(-2.41765, 0, 0, 2.41765, 0, 5.4)
    path.lineTo(0, height - 4)
    path.cubicTo(0, height - 1.79086, 1.79086, height, 4, height)
    path.cubicTo(6.20914, height, 8, height - 1.79086, 8, height - 4)
    path.lineTo(8, 5.4)
    path.cubicTo(8, 2.41765, 10.41765, 0, 13.4, 0)
    path.closeSubpath()
    return path


DRIP_PATHS = {height: drip_outline(height) for _, height, _ in DRIPS}


def paint_allowed(button):
    widget = button
    enabled = False
    while widget is not None:
        if widget.property("wetPaintDisabled") or widget.objectName() == "sidebar":
            return False
        enabled = enabled or bool(widget.property("wetPaintEnabled"))
        widget = widget.parentWidget()
    return enabled


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
        # Only fade in visibility; do not distort the reference's initial .75 scale.
        reveal = min(1, elapsed / .15)
        for left, height, delay in DRIPS:
            scale, drop_y, opacity = drip_frame(elapsed, delay)
            painter.save()
            painter.translate(rect.left() + left * rect.width(), rect.top() + rect.height() * .99)
            # The CSS parent scaleY applies to joins, body AND falling droplet.
            painter.scale(1, scale)
            painter.setOpacity(reveal)
            painter.setBrush(color)
            painter.drawPath(DRIP_PATHS[height])
            if opacity > 0:
                painter.setOpacity(opacity * reveal)
                painter.drawEllipse(QRectF(0, height + drop_y, 8, 8))
            painter.restore()


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
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
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
                    or not paint_allowed(button)):
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
                or not button.isEnabled() or not paint_allowed(button) or self.reduce_motion):
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
