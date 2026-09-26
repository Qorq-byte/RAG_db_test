"""Native, offline photo-card choreography for the desktop entrance."""

from dataclasses import dataclass
import math
from pathlib import Path
from random import Random

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
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


def _ease(value: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, value))) ** 3


def card_poses(width: float, height: float, progress: float) -> tuple[CardPose, ...]:
    """Scatter → line → ring. Geometry stays deterministic across window resizes."""
    progress = max(0.0, min(1.0, progress))
    scale = max(0.45, min(1.0, width / 1280, height / 800))
    radius = min(width * 0.35, height * 0.35, 300)
    spacing = min(70, (width - 72) / CARD_COUNT)
    line_scale = min(scale, spacing / 70)
    poses = []
    for index, (sx, sy, rotation) in enumerate(SCATTER):
        line_x = (index - (CARD_COUNT - 1) / 2) * spacing
        if progress < 0.55:
            t = _ease((progress - 0.125) / 0.425)
            x, y = sx * width * (1 - t) + line_x * t, sy * height * (1 - t)
            angle = rotation * (1 - t)
            size = scale * 0.65 * (1 - t) + line_scale * t
            opacity = _ease(progress / 0.125)
        else:
            t = _ease((progress - 0.55) / 0.45)
            angle_degrees = index * 360 / CARD_COUNT - 90
            radians = math.radians(angle_degrees)
            x = line_x * (1 - t) + math.cos(radians) * radius * t
            y = math.sin(radians) * radius * t
            # Use the shortest rotation; no card makes a full turn unnecessarily.
            final_rotation = (angle_degrees + 180) % 360 - 90
            angle, size, opacity = final_rotation * t, line_scale * (1 - t) + scale * t, 1.0
        poses.append(CardPose(width / 2 + x, height / 2 + y, angle, size, opacity))
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
        self.motion_enabled = True
        self.flip_value = 0.0
        self.flip = QVariantAnimation(self)
        self.flip.setDuration(420)
        self.flip.setEasingCurve(QEasingCurve.Type.InOutCubic)
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
        self.setZValue(2)
        self._animate_flip(1.0)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
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
        painter.scale(max(0.015, abs(math.cos(self.flip_value * math.pi))), 1)
        rect = QRectF(-30, -42.5, 60, 85)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 20, 30, 16))
        painter.drawRoundedRect(rect.translated(0, 4).adjusted(-2, -2, 2, 2), 7, 7)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.setClipPath(path)
        if self.flip_value < 0.5 and not self.pixmap.isNull():
            source = QRectF((self.pixmap.width() - 180) / 2, (self.pixmap.height() - 255) / 2, 180, 255)
            painter.drawPixmap(rect, self.pixmap, source)
        else:
            painter.fillRect(rect, QColor("#18202b"))
            painter.setPen(QColor("#65d2e5"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            painter.drawText(QRectF(-30, -17, 60, 25), Qt.AlignmentFlag.AlignCenter, "RAG")
            painter.setPen(QColor("#e8edf4"))
            painter.setFont(QFont("Microsoft YaHei UI", 5))
            painter.drawText(QRectF(-30, 10, 60, 16), Qt.AlignmentFlag.AlignCenter, "连接你的知识")
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(255, 255, 255, 130))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


class WelcomeScene(QGraphicsView):
    def __init__(self, parent=None, *, asset_directory: Path = ASSET_DIRECTORY) -> None:
        super().__init__(parent)
        self.setObjectName("welcomeScene")
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.canvas = QGraphicsScene(self)
        self.setScene(self.canvas)
        self.cards = [PhotoCard(index, asset_directory) for index in range(CARD_COUNT)]
        for card in self.cards:
            self.canvas.addItem(card)
        self.progress = 0.0
        self.setAccessibleName("图片卡片开场动画")

    def set_progress(self, progress: float) -> None:
        self.progress = float(progress)
        width, height = self.viewport().width(), self.viewport().height()
        self.canvas.setSceneRect(0, 0, width, height)
        for card, pose in zip(self.cards, card_poses(width, height, progress), strict=True):
            card.setPos(pose.x, pose.y)
            card.setRotation(pose.rotation)
            card.setScale(pose.scale)
            card.setOpacity(pose.opacity)

    def set_reduce_motion(self, enabled: bool) -> None:
        for card in self.cards:
            card.motion_enabled = not enabled
            if enabled:
                card.stop_motion()

    def stop_hover_animations(self) -> None:
        for card in self.cards:
            card.stop_motion()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_progress(self.progress)
