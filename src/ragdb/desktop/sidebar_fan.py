"""Offline native port of the reference seven-slot card-fan carousel."""

from dataclasses import dataclass
import json
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform, QPalette
from PySide6.QtWidgets import QWidget, QToolButton, QSizePolicy, QLabel


from ragdb.desktop.theme import DARK, LIGHT


ASSETS = Path(__file__).parent / "assets" / "sidebar_fan"
# Exact seven-slot reference: rotation, scale, horizontal rem, vertical rem, layer.
FAN_POSITIONS = (
    (-21, .7756, -30, 7.3, 1), (-14, .8498, -22, 4, 2),
    (-7, .9346, -11, 1.3, 3), (0, 1, 0, 0, 10),
    (7, .9346, 11, 1.3, 3), (14, .8498, 22, 4, 2), (21, .7756, 30, 7.3, 1),
)


@dataclass(frozen=True)
class FanPose:
    x: float
    y: float
    rotation: float
    scale: float
    opacity: float = 1
    layer: int = 0


def fan_pose(slot: int, count: int, hovered: int | None = None) -> FanPose:
    center = count // 2
    if count == 7:
        rot, scale, x, y, layer = FAN_POSITIONS[slot]
    else:
        distance = (slot - center) / center if center else 0
        rot, scale = distance * 21, 1 - .2244 * distance ** 2
        x, y, layer = distance * 30, distance ** 2 * 7.3, 10 - abs(slot - center)
    if hovered is not None:
        distance = abs(slot - hovered)
        if slot == hovered:
            y -= 2.5
            scale *= 1.08
        else:
            normalized = (slot - center) / center if center else 0
            push = 8 * (1 - abs(normalized)) * (1 + .2 * max(0, 3 - distance))
            sign = -1 if slot < hovered else 1
            x += sign * push
            rot += sign * 3 / (distance + 1)
            if (slot == count - 1 and hovered < center) or (slot == 0 and hovered > center):
                y -= 1
    # Reference's narrow-width spread, then fit the complete composition uniformly
    # into the sidebar. Only the outer fit changes when the sidebar is resized.
    return FanPose(x * 16 * .28, y * 16 * .65, rot, scale, 1, layer)


class FanCanvas(QWidget):
    center_changed = Signal(int)
    busy_changed = Signal(bool)

    def __init__(self, parent=None, *, assets: Path = ASSETS, reduce_motion=False):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("风景扇形卡片，左右方向键切换")
        self.setToolTip("悬停展开卡片，使用下方箭头或左右方向键切换")
        manifest = json.loads((assets / "sources.json").read_text(encoding="utf-8")) if (assets / "sources.json").exists() else []
        self.names = [item["alt"] for item in manifest]
        self.photos = [QPixmap(str(assets / item["file"])) for item in manifest]
        self.count = len(self.photos)
        self.center = 3 if self.count > 7 else self.count // 2
        self.poses = [FanPose(0, 125, 0, .5, 0) for _ in self.photos]
        self.reduce_motion = reduce_motion
        self.busy = False
        self.entered = False
        self.active_slot = None
        self.transitions = {}
        self.animation = QVariantAnimation(self)
        self.animation.valueChanged.connect(self._frame)
        self.animation.finished.connect(self._finished)
        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.setInterval(50)
        self.leave_timer.timeout.connect(lambda: self.set_hover(None))
        self.hit_paths = {}

    def visible_map(self):
        if self.count <= 7:
            return {i: i for i in range(self.count)}
        return {(self.center + slot - 3) % self.count: slot for slot in range(7)}

    def _set_busy(self, busy):
        self.busy = busy
        self.busy_changed.emit(busy)

    def _animate(self, transitions, busy=False):
        self.animation.stop()
        self.transitions = transitions
        self._set_busy(busy)
        if not transitions:
            self._finished()
            return
        duration = max(delay + duration for _, _, delay, duration, _ in transitions.values())
        self.animation.setDuration(int(duration))
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(float(duration))
        if self.reduce_motion or not self.isVisible():
            self._frame(duration)
            self._finished()
        else:
            self.animation.start()

    def _frame(self, elapsed):
        for index, (start, target, delay, duration, kind) in self.transitions.items():
            t = max(0, min(1, (float(elapsed) - delay) / duration))
            curve = QEasingCurve(kind)
            if kind == QEasingCurve.Type.OutElastic:
                curve.setAmplitude(1.05)
                curve.setPeriod(.78)
            amount = curve.valueForProgress(t)
            values = [a + (b - a) * amount for a, b in zip(
                (start.x, start.y, start.rotation, start.scale, start.opacity),
                (target.x, target.y, target.rotation, target.scale, target.opacity))]
            self.poses[index] = FanPose(*values, target.layer)
        self.update()

    def _finished(self):
        for index, (_, target, *_rest) in self.transitions.items():
            self.poses[index] = target
        self.update()
        self.entered = True
        self._set_busy(False)

    def cycle(self, direction):
        if self.busy or self.count <= 7:
            return
        self.leave_timer.stop()
        self.active_slot = None
        old = self.visible_map()
        self.center = (self.center + direction) % self.count
        new = self.visible_map()
        transitions = {}
        for i in old.keys() | new.keys():
            start = self.poses[i]
            if i in new:
                target = fan_pose(new[i], min(7, self.count))
                if i not in old:
                    start = FanPose(direction * 640, target.y, direction * 30, .5, 0)
                transitions[i] = (start, target, 0, 600 if i not in old else 500, QEasingCurve.Type.OutCubic)
            else:
                target = FanPose(-direction * 640, start.y, -direction * 30, .5, 0)
                transitions[i] = (start, target, 0, 400, QEasingCurve.Type.InCubic)
        self.center_changed.emit(self.center)
        self._animate(transitions, busy=True)

    def set_hover(self, slot):
        if self.busy or slot == self.active_slot:
            return
        self.active_slot = slot
        transitions = {}
        count = min(7, self.count)
        for i, position in self.visible_map().items():
            delay = abs(position - (slot if slot is not None else count // 2)) * 20
            transitions[i] = (self.poses[i], fan_pose(position, count, slot), delay, 500, QEasingCurve.Type.OutElastic)
        self._animate(transitions)

    def set_reduce_motion(self, enabled):
        self.reduce_motion = enabled
        if enabled and self.transitions:
            self.animation.stop()
            self._frame(self.animation.duration())
            self._finished()

    def mouseMoveEvent(self, event):
        self.leave_timer.stop()
        for i in sorted(self.hit_paths, key=lambda i: self.poses[i].layer, reverse=True):
            if self.hit_paths[i].contains(event.position()):
                self.set_hover(self.visible_map().get(i))
                self.setAccessibleDescription(self.names[i])
                break
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.leave_timer.start()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.cycle(-1 if event.key() == Qt.Key.Key_Left else 1)
            event.accept()
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.entered:
            transitions = {i: (self.poses[i], fan_pose(slot, min(7, self.count)),
                                200 + slot * 60, 1200, QEasingCurve.Type.OutElastic)
                           for i, slot in self.visible_map().items()}
            self._animate(transitions, busy=True)

    def hideEvent(self, event):
        self.animation.stop()
        self.leave_timer.stop()
        self.active_slot = None
        for i in range(self.count):
            slot = self.visible_map().get(i)
            self.poses[i] = fan_pose(slot, min(7, self.count)) if slot is not None else FanPose(0, 0, 0, .5, 0)
        self._set_busy(False)
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        fit = min(self.width() / 470, self.height() / 370)
        self.hit_paths = {}
        rect = QRectF(-80, -112, 160, 224)
        for i in sorted(range(self.count), key=lambda i: self.poses[i].layer):
            pose = self.poses[i]
            if pose.opacity <= .001:
                continue
            transform = QTransform()
            transform.translate(self.width() / 2 + pose.x * fit, self.height() / 2 + (pose.y - 36) * fit)
            transform.rotate(pose.rotation)
            transform.scale(pose.scale * fit, pose.scale * fit)
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            if i in self.visible_map():
                self.hit_paths[i] = transform.map(path)
            painter.save()
            painter.setTransform(transform)
            painter.setOpacity(max(0, min(1, pose.opacity)))
            painter.setPen(Qt.PenStyle.NoPen)
            for spread in range(8, 0, -2):
                painter.setBrush(QColor(0, 0, 0, 7))
                painter.drawRoundedRect(rect.translated(0, 5).adjusted(-spread, -spread, spread, spread), 12, 12)
            painter.setClipPath(path)
            photo = self.photos[i]
            if photo.isNull():
                painter.fillRect(rect, QColor("#687386"))
                painter.setPen(QColor("white"))
                painter.drawText(rect.adjusted(12, 12, -12, -12), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.names[i])
            else:
                ratio = max(160 / photo.width(), 224 / photo.height())
                source = QRectF((photo.width() - 160 / ratio) / 2, (photo.height() - 224 / ratio) / 2, 160 / ratio, 224 / ratio)
                painter.drawPixmap(rect, photo, source)
            painter.restore()
        if self.hasFocus():
            painter.setPen(QPen(self.palette().highlight().color(), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)


class PageDots(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        canvas.center_changed.connect(lambda _: self.update())
        self.setAccessibleName("卡片位置")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        step = min(7, self.width() / max(1, self.canvas.count))
        for i in range(self.canvas.count):
            color = self.palette().windowText().color()
            color.setAlpha(200 if i == self.canvas.center else 45)
            painter.setBrush(color)
            radius = 2.6 if i == self.canvas.center else 2
            painter.drawEllipse(QPointF(self.width() / 2 + (i - (self.canvas.count - 1) / 2) * step, self.height() / 2), radius, radius)


class FanCarousel(QWidget):
    def __init__(self, parent=None, *, reduce_motion=False, assets=ASSETS):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.setMinimumHeight(0)
        self.setMaximumHeight(300)
        self.canvas = FanCanvas(self, assets=assets, reduce_motion=reduce_motion)
        self.previous = QToolButton(self)
        self.next = QToolButton(self)
        self.dots = PageDots(self.canvas, self)
        self.compact_hint = QLabel("增大窗口以查看卡片", self)
        self.compact_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.compact_hint.setProperty("muted", True)
        self.compact_hint.setStyleSheet("font-size: 11px;")
        for button, text, label, direction in ((self.previous, "‹", "上一张卡片", -1), (self.next, "›", "下一张卡片", 1)):
            button.setText(text)
            button.setAccessibleName(label)
            button.setToolTip(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet("QToolButton { border-radius: 16px; border: 1px solid palette(mid); background: palette(alternate-base); font-size: 22px; } QToolButton:hover, QToolButton:focus { border: 2px solid palette(highlight); } QToolButton:pressed { background: palette(midlight); }")
            button.clicked.connect(lambda _checked=False, d=direction: self.canvas.cycle(d))
        self.canvas.busy_changed.connect(self._busy_changed)
        self.canvas.center_changed.connect(self._describe_position)
        self._describe_position(self.canvas.center)

    def set_dark_mode(self, dark):
        colors = DARK if dark else LIGHT
        palette = self.palette()
        for role, key in ((QPalette.ColorRole.WindowText, "text"),
                          (QPalette.ColorRole.Mid, "border"),
                          (QPalette.ColorRole.AlternateBase, "raised"),
                          (QPalette.ColorRole.Highlight, "accent"),
                          (QPalette.ColorRole.Midlight, "accent_soft")):
            palette.setColor(role, QColor(colors[key]))
        self.setPalette(palette)
        self.dots.update()

    def sizeHint(self):
        return QSize(212, 240)

    def _describe_position(self, center):
        self.dots.setAccessibleDescription(f"第 {center + 1} 张，共 {self.canvas.count} 张")

    def _busy_changed(self, busy):
        self.previous.setEnabled(not busy)
        self.next.setEnabled(not busy)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        compact = h < 112
        self.compact_hint.setGeometry(self.rect())
        self.compact_hint.setVisible(compact and self.canvas.count > 0)
        pagination = self.canvas.count > 7 and not compact
        self.canvas.setGeometry(0, 0, w, max(0, h - (40 if pagination else 0)))
        self.canvas.setVisible(not compact)
        for widget in (self.previous, self.next, self.dots):
            widget.setVisible(pagination)
        controls = min(w, 164)
        left = (w - controls) // 2
        self.previous.setGeometry(left, h - 34, 32, 32)
        self.next.setGeometry(left + controls - 32, h - 34, 32, 32)
        self.dots.setGeometry(left + 36, h - 34, max(0, controls - 72), 32)
