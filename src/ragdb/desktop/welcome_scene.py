"""Native, offline photo-card choreography for the desktop entrance."""

from dataclasses import dataclass
import math
from pathlib import Path
from random import Random
from time import monotonic

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, QTimer, Signal, QEvent
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsObject, QGraphicsScene, QGraphicsView


ASSET_DIRECTORY = Path(__file__).parent / "assets" / "welcome"
CARD_COUNT = 20
_random = Random(42)
SCATTER = tuple((_random.uniform(-0.46, 0.46), _random.uniform(-0.36, 0.36),
                 _random.uniform(-85, 85)) for _ in range(CARD_COUNT))


@dataclass(frozen=True)
class CardPose:
    x: float
    y: float
    rotation: float
    scale: float
    opacity: float


MAX_SCROLL = 3000.0


def card_poses(width: float, height: float, progress: float,
               morph: float = 0, sweep: float = 0, parallax: float = 0) -> tuple[CardPose, ...]:
    """Targets ported from scroll-morph-hero; coordinates are viewport-relative."""
    poses = []
    narrow = width < 768
    radius = min(width, height) * .35
    radius = min(radius, 350)
    arc_radius = min(width, height * 1.5) * (1.4 if narrow else 1.1)
    spread = 100 if narrow else 130
    for i, (sx, sy, rotation) in enumerate(SCATTER):
        if progress < .125:
            pose = CardPose(sx / .46 * 750, sy / .36 * 500, rotation, .6, 0)
        elif progress < .625:
            pose = CardPose(i * 70 - 700, 0, 0, 1, 1)
        else:
            angle = i / CARD_COUNT * 360
            rad = math.radians(angle)
            arc_angle = -90 - spread / 2 + i * spread / 19 - sweep * spread * .8
            arc_rad = math.radians(arc_angle)
            cx, cy = math.cos(rad) * radius, math.sin(rad) * radius
            ax = math.cos(arc_rad) * arc_radius + parallax
            ay = math.sin(arc_rad) * arc_radius + arc_radius + height * (.35 if narrow else .25)
            pose = CardPose(cx + (ax - cx) * morph, cy + (ay - cy) * morph,
                            angle + 90 + (arc_angle - angle) * morph,
                            1 + ((1.4 if narrow else 1.8) - 1) * morph, 1)
        poses.append(CardPose(width / 2 + pose.x, height / 2 + pose.y,
                              pose.rotation, pose.scale, pose.opacity))
    return tuple(poses)


class PhotoCard(QGraphicsObject):
    def __init__(self, index: int, asset_directory: Path) -> None:
        super().__init__()
        self.index = index
        self.pixmap = QPixmap(str(asset_directory / f"{index + 1:02}.jpg"))
        if not self.pixmap.isNull():
            self.pixmap = self.pixmap.scaled(180, 255, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                             Qt.TransformationMode.SmoothTransformation)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hovered = False
        self.motion_enabled = True
        self.flip_value = 0.0
        self.flip = QVariantAnimation(self)
        self.flip.setDuration(600)
        self.flip.setEasingCurve(QEasingCurve.Type.OutBack)
        self.flip.valueChanged.connect(self._flip_changed)

    def boundingRect(self) -> QRectF:
        return QRectF(-36, -46.5, 72, 99)

    def _flip_changed(self, value) -> None:
        self.flip_value = float(value)
        self.update()

    def _animate_flip(self, target: float) -> None:
        if not self.motion_enabled:
            return
        self.flip.stop()
        self.flip.setStartValue(self.flip_value)
        self.flip.setEndValue(target)
        self.flip.start()

    def hoverEnterEvent(self, event) -> None:
        self.hovered = True
        self.setZValue(2)
        self._animate_flip(1.0)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.hovered = False
        self.setZValue(0)
        self._animate_flip(0.0)
        super().hoverLeaveEvent(event)

    def stop_motion(self) -> None:
        self.flip.stop()
        self.flip_value = 0.0
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        angle = self.flip_value * math.pi
        # Project a Y-axis flip with the reference's 1000px perspective.
        # Back-face text is painted upright after passing the half-turn.
        painter.setTransform(QTransform(max(.015, abs(math.cos(angle))), 0,
                                        math.sin(angle) / 1000, 0, 1, 0, 0, 0, 1), True)
        rect = QRectF(-30, -42.5, 60, 85)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 20, 30, 16))
        painter.drawRoundedRect(rect.translated(0, 4).adjusted(-2, -2, 2, 2), 7, 7)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.setClipPath(path)
        if self.flip_value < 0.5 and not self.pixmap.isNull():
            source = QRectF((self.pixmap.width() - 180) / 2, (self.pixmap.height() - 255) / 2, 180, 255)
            painter.drawPixmap(rect, self.pixmap, source)
            if not self.hovered:
                painter.fillRect(rect, QColor(0, 0, 0, 26))
        else:
            painter.fillRect(rect, QColor("#18202b"))
            painter.setPen(QColor("#65d2e5"))
            painter.setFont(QFont("Segoe UI", 6, QFont.Weight.DemiBold))
            painter.drawText(QRectF(-30, -17, 60, 25), Qt.AlignmentFlag.AlignCenter, "View")
            painter.setPen(QColor("#e8edf4"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(-30, 10, 60, 16), Qt.AlignmentFlag.AlignCenter, "Details")
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(255, 255, 255, 130))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)


class WelcomeScene(QGraphicsView):
    frame_changed = Signal()

    def __init__(self, parent=None, *, asset_directory: Path = ASSET_DIRECTORY) -> None:
        super().__init__(parent)
        self.setObjectName("welcomeScene")
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.canvas = QGraphicsScene(self)
        self.setScene(self.canvas)
        self.cards = [PhotoCard(i, asset_directory) for i in range(CARD_COUNT)]
        for card in self.cards:
            self.canvas.addItem(card)
        self.progress = self.virtual_scroll = 0.0
        self.values = [0.0, 0.0, 0.0]  # morph, bounded sweep, horizontal parallax
        self.velocities = [0.0, 0.0, 0.0]
        self.pointer = 0.0
        self.reduced = False
        self.locked = False
        self.settled = False
        self._touch_y = None
        self._poses = None
        self._pose_velocities = [[0.0] * 5 for _ in self.cards]
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self._last_tick = monotonic()
        self.setAccessibleName("滚轮探索图片；方向键和翻页键滚动，Home 返回，End 到达结尾")
        self.set_progress(0)

    def _wake(self):
        self.settled = False
        if self.isVisible() and not self.timer.isActive():
            self._last_tick = monotonic()
            self.timer.start()

    def set_progress(self, progress: float) -> None:
        self.progress = float(progress)
        self._wake()
        if self._poses is None:
            self._render(snap=True)

    def scroll_by(self, delta: float) -> None:
        if self.locked:
            return
        self.virtual_scroll = max(0.0, min(MAX_SCROLL, self.virtual_scroll + delta))
        self._wake()
        self.frame_changed.emit()

    def wheelEvent(self, event) -> None:
        # Qt positive deltas mean up; pixelDelta preserves precision touchpad input.
        delta = event.pixelDelta().y() if not event.pixelDelta().isNull() else event.angleDelta().y()
        self.scroll_by(-delta)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        self.pointer = max(-100, min(100, (event.position().x() / max(1, self.viewport().width()) * 2 - 1) * 100))
        self._wake()
        super().mouseMoveEvent(event)

    def viewportEvent(self, event):
        kind = event.type()
        if kind in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd, QEvent.Type.TouchCancel):
            points = event.points()
            if kind == QEvent.Type.TouchBegin and points:
                self._touch_y = points[0].position().y()
            elif kind == QEvent.Type.TouchUpdate and points and self._touch_y is not None:
                y = points[0].position().y()
                self.scroll_by(self._touch_y - y)
                self._touch_y = y
            else:
                self._touch_y = None
            event.accept()
            return True
        return super().viewportEvent(event)

    def _tick(self):
        elapsed = min(.05, monotonic() - self._last_tick)
        self._last_tick = monotonic()
        targets = [min(1, self.virtual_scroll / 600),
                   max(0, (self.virtual_scroll - 600) / 2400), self.pointer]
        # Fixed small integration steps avoid unstable jumps after a slow frame.
        steps = max(1, math.ceil(elapsed / .008))
        dt = elapsed / steps
        for _ in range(steps):
            for i, target in enumerate(targets):
                stiffness = 30 if i == 2 else 40
                self.velocities[i] += (stiffness * (target - self.values[i]) - 20 * self.velocities[i]) * dt
                self.values[i] += self.velocities[i] * dt
        quiet = all(abs(a - b) < (.1 if i == 2 else .0005) and abs(self.velocities[i]) < (.1 if i == 2 else .001)
                    for i, (a, b) in enumerate(zip(self.values, targets)))
        if quiet or self.reduced:
            self.values = targets
            self.velocities = [0.0] * 3
        cards_quiet = self._render(dt=elapsed, snap=self.reduced)
        self.settled = quiet and cards_quiet
        if self.settled or self.reduced:
            self.settled = True
            self.timer.stop()
        self.frame_changed.emit()

    def _render(self, *, dt=0.0, snap=False):
        width, height = self.viewport().width(), self.viewport().height()
        self.canvas.setSceneRect(0, 0, width, height)
        targets = card_poses(width, height, self.progress, *self.values)
        if self._poses is None or snap:
            self._poses = [[p.x, p.y, p.rotation, p.scale, p.opacity] for p in targets]
            self._pose_velocities = [[0.0] * 5 for _ in self.cards]
        quiet = True
        for i, (card, pose) in enumerate(zip(self.cards, targets)):
            target = [pose.x, pose.y, pose.rotation, pose.scale, pose.opacity]
            for j, end in enumerate(target):
                value, velocity = self._poses[i][j], self._pose_velocities[i][j]
                steps = max(1, math.ceil(dt / .008))
                for _ in range(steps):
                    velocity += (40 * (end - value) - 15 * velocity) * dt / steps
                    value += velocity * dt / steps
                tolerance = .15 if j < 3 else .001
                if abs(end - value) < tolerance and abs(velocity) < tolerance:
                    value, velocity = end, 0.0
                else:
                    quiet = False
                self._poses[i][j], self._pose_velocities[i][j] = value, velocity
            x, y, rotation, scale, opacity = self._poses[i]
            card.setPos(x, y)
            card.setRotation(rotation)
            card.setScale(scale)
            card.setOpacity(max(0, min(1, opacity)))
        return quiet

    def jump_to_end(self):
        self.progress = 1.0
        self.virtual_scroll = MAX_SCROLL
        self.values = [1.0, 1.0, self.pointer]
        self.velocities = [0.0] * 3
        self._render(snap=True)
        self.settled = True
        self.timer.stop()
        self.frame_changed.emit()

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduced = enabled
        for card in self.cards:
            card.motion_enabled = not enabled
            if enabled:
                card.stop_motion()
        self._wake()

    def stop_hover_animations(self) -> None:
        for card in self.cards:
            card.stop_motion()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render(snap=True)
        self._wake()

    def hideEvent(self, event):
        self.timer.stop()
        self.stop_hover_animations()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._wake()
