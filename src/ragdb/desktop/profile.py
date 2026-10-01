"""Private, per-account desktop profile and its sidebar control."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget, QWidgetAction,
)


@dataclass(frozen=True)
class ProfileData:
    name: str = ""
    interests: str = ""


class ProfileStore:
    """Only editable presentation fields live beside this account's knowledge base."""

    def __init__(self, account_dir: Path | None):
        self.account_dir = account_dir

    @property
    def metadata_path(self) -> Path | None:
        return self.account_dir / "profile.json" if self.account_dir is not None else None

    @property
    def avatar_path(self) -> Path | None:
        return self.account_dir / "profile-avatar.png" if self.account_dir is not None else None

    def load(self) -> ProfileData:
        path = self.metadata_path
        if path is None or not path.exists():
            return ProfileData()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            name, interests = data.get("name", ""), data.get("interests", "")
            if not isinstance(name, str) or not isinstance(interests, str):
                raise ValueError
            return ProfileData(name[:80], interests[:1000])
        except (OSError, ValueError):
            return ProfileData()

    def save(self, profile: ProfileData, avatar: QImage | None = None) -> None:
        path = self.metadata_path
        if path is None:
            raise OSError("未找到当前账号的数据目录。")
        self.account_dir.mkdir(parents=True, exist_ok=True)
        if avatar is not None:
            target = self.avatar_path
            temporary = target.with_suffix(".tmp.png")
            if not avatar.save(str(temporary), "PNG"):
                raise OSError("无法保存头像。")
            os.replace(temporary, target)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"name": profile.name, "interests": profile.interests}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def avatar(self) -> QPixmap:
        path = self.avatar_path
        if path is not None and path.exists():
            return QPixmap(str(path))
        return QPixmap()


class ProfileButton(QPushButton):
    """Account card from the supplied dropdown reference, sized for the sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.name = "个人账号"
        self.email = ""
        self.avatar = QPixmap()
        self.collapsed = False
        self.dark = False
        self.menu_open = False
        self.setObjectName("profileTrigger")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(66)
        self.setAccessibleName("打开个人资料菜单")
        self.setToolTip("个人资料、模型和设置")
        self.setStyleSheet("QPushButton#profileTrigger { background: transparent; border: none; padding: 0; }")

    def set_profile(self, profile: ProfileData, email: str, avatar: QPixmap):
        self.name = profile.name.strip() or (email.split("@", 1)[0] if email else "个人账号")
        self.email = email
        self.avatar = avatar
        self.update()

    def set_collapsed(self, collapsed: bool):
        self.collapsed = collapsed
        self.setFixedHeight(44 if collapsed else 66)
        self.update()

    def set_dark_mode(self, dark: bool):
        self.dark = dark
        self.update()

    def set_menu_open(self, open_: bool):
        self.menu_open = open_
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse() or self.hasFocus() or self.menu_open
        card = self.rect().adjusted(1, 1, -1 if self.collapsed else -12, -1)
        surface = QColor("#24272d" if hovered and self.dark else
                         "#1b1e24" if self.dark else
                         "#fafbfc" if hovered else "#ffffff")
        border = QColor("#5d6674" if hovered and self.dark else
                        "#bfc7d2" if hovered else "#373c45" if self.dark else "#d9dde3")
        painter.setBrush(surface)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(card, 15, 15)
        avatar_size = 40 if not self.collapsed else 34
        avatar_x = (card.width() - avatar_size) // 2 if self.collapsed else card.right() - avatar_size - 10
        avatar_y = (self.height() - avatar_size) // 2
        avatar_rect = QRectF(avatar_x, avatar_y, avatar_size, avatar_size)
        gradient = QLinearGradient(avatar_rect.topLeft(), avatar_rect.bottomRight())
        gradient.setColorAt(0, QColor("#9b5de5"))
        gradient.setColorAt(0.52, QColor("#ee6eaa"))
        gradient.setColorAt(1, QColor("#f6a44d"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(avatar_rect)
        inset = avatar_rect.adjusted(2.5, 2.5, -2.5, -2.5)
        painter.setBrush(QColor("#1b1e24" if self.dark else "#ffffff"))
        painter.drawEllipse(inset)
        if not self.avatar.isNull():
            path = QPainterPath()
            path.addEllipse(inset.adjusted(1, 1, -1, -1))
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(inset.toRect(), self.avatar)
            painter.restore()
        else:
            painter.setPen(QColor("#efdaff" if self.dark else "#7854a4"))
            font = QFont("Microsoft YaHei UI", 10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(inset, Qt.AlignmentFlag.AlignCenter, self.name[:1].upper())
        if not self.collapsed:
            name_font = QFont("Microsoft YaHei UI", 10)
            name_font.setBold(True)
            painter.setFont(name_font)
            painter.setPen(QColor("#f0f0f1" if self.dark else "#20232b"))
            available = max(30, avatar_x - 24)
            painter.drawText(13, 15, available, 18, Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideRight, available))
            painter.setPen(QColor("#a8aab1" if self.dark else "#717780"))
            painter.setFont(QFont("Microsoft YaHei UI", 8))
            painter.drawText(13, 35, available, 17, Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(self.email, Qt.TextElideMode.ElideRight, available))
            curve = QPainterPath(QPointF(self.width() - 9, self.height() / 2 - 9))
            curve.cubicTo(self.width() - 3, self.height() / 2 - 4,
                          self.width() - 3, self.height() / 2 + 4,
                          self.width() - 9, self.height() / 2 + 9)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#5b8ff2" if self.menu_open else
                                    "#8f95a0" if self.dark else "#a3aab4"), 1.6))
            painter.drawPath(curve)


class ProfileMenuIcon(QWidget):
    """Small line icons sized and colored like the reference dropdown."""

    def __init__(self, kind: str, *, dark: bool = False, danger: bool = False, parent=None):
        super().__init__(parent)
        self.kind, self.dark, self.danger = kind, dark, danger
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_dark_mode(self, dark: bool):
        self.dark = dark
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#e45b65" if self.danger else "#cbd0d9" if self.dark else "#535c68")
        painter.setPen(QPen(color, 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "profile":
            painter.drawEllipse(QRectF(6, 2, 6, 6))
            painter.drawArc(QRectF(3, 8, 12, 8), 0, 180 * 16)
        elif self.kind == "model":
            star = QPainterPath(QPointF(9, 1))
            for x, y in ((11, 7), (17, 9), (11, 11), (9, 17), (7, 11), (1, 9), (7, 7)):
                star.lineTo(x, y)
            star.closeSubpath()
            painter.drawPath(star)
        elif self.kind == "settings":
            painter.drawEllipse(QRectF(6, 6, 6, 6))
            for x1, y1, x2, y2 in ((9, 1, 9, 4), (9, 14, 9, 17), (1, 9, 4, 9),
                                    (14, 9, 17, 9), (3, 3, 5, 5), (13, 13, 15, 15),
                                    (13, 5, 15, 3), (3, 15, 5, 13)):
                painter.drawLine(x1, y1, x2, y2)
        elif self.kind == "logout":
            painter.drawLine(2, 3, 2, 15)
            painter.drawLine(2, 3, 9, 3)
            painter.drawLine(2, 15, 9, 15)
            painter.drawLine(7, 9, 16, 9)
            painter.drawLine(12, 5, 16, 9)
            painter.drawLine(12, 13, 16, 9)


class ProfileMenuRow(QPushButton):
    def __init__(self, label: str, kind: str, *, danger: bool = False, dark: bool = False):
        super().__init__()
        self.kind, self.danger, self.dark = kind, danger, dark
        self.setObjectName("profileMenuRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(label)
        self.setFixedHeight(43)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(9)
        self.glyph = ProfileMenuIcon(kind, dark=dark, danger=danger, parent=self)
        layout.addWidget(self.glyph)
        self.label = QLabel(label, self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.label)
        layout.addStretch(1)
        self.badge = QLabel(self)
        self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.badge.setObjectName("profileModelBadge")
        self.badge.hide()
        layout.addWidget(self.badge)
        self.set_dark_mode(dark)

    def set_value(self, value: str):
        self.badge.setText(self.badge.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, 105))
        self.badge.setToolTip(value)
        self.badge.setVisible(bool(value))

    def set_dark_mode(self, dark: bool):
        self.dark = dark
        self.glyph.set_dark_mode(dark)
        text = "#ededef" if dark else "#24272e"
        hover = "#30343e" if dark else "#f2f4f6"
        base = "#3b1e25" if dark else "#fff0f1"
        danger_hover = "#51232d" if dark else "#ffe4e7"
        self.setStyleSheet(f"""
            QPushButton#profileMenuRow {{ background: {base if self.danger else 'transparent'};
                border: 1px solid transparent; border-radius: 11px; padding: 0; }}
            QPushButton#profileMenuRow:hover, QPushButton#profileMenuRow:focus {{
                background: {danger_hover if self.danger else hover};
                border-color: {'#bd6670' if self.danger else '#555d69' if dark else '#dce0e6'}; }}
            QLabel {{ background: transparent; border: none; color: {'#e45b65' if self.danger else text};
                font-size: 12px; font-weight: 600; }}
            QLabel#profileModelBadge {{ color: {'#91adff' if dark else '#3464c5'};
                background: {'#1c2c4a' if dark else '#edf3ff'};
                border: 1px solid {'#354a73' if dark else '#dce7ff'};
                border-radius: 6px; padding: 3px 6px; font-size: 10px; }}
        """)


def add_profile_menu_row(menu: QMenu, label: str, kind: str, *,
                         danger: bool = False) -> tuple[QWidgetAction, ProfileMenuRow]:
    row = ProfileMenuRow(label, kind, danger=danger)
    action = QWidgetAction(menu)
    action.setText(label)
    action.setDefaultWidget(row)
    menu.addAction(action)
    row.clicked.connect(lambda: (menu.hide(), action.trigger()))
    return action, row


class ProfileDialog(QDialog):
    saved = Signal(object)

    def __init__(self, store: ProfileStore, email: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.email = email
        self.pending_avatar: QImage | None = None
        profile = store.load()
        self.setWindowTitle("个人资料")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)
        title = QLabel("个人资料")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)
        description = QLabel("头像、称呼和兴趣保存在本机当前账号的数据目录。")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.avatar_button = QPushButton("更换头像…")
        self.avatar_button.clicked.connect(self._choose_avatar)
        layout.addWidget(self.avatar_button)
        form = QFormLayout()
        self.email_field = QLineEdit(email)
        self.email_field.setReadOnly(True)
        self.email_field.setAccessibleName("账号邮箱，只读")
        self.name_field = QLineEdit(profile.name)
        self.name_field.setMaxLength(80)
        self.name_field.setPlaceholderText("希望显示的称呼")
        self.interests_field = QTextEdit(profile.interests)
        self.interests_field.setPlaceholderText("例如：机器学习、阅读、科研")
        self.interests_field.setFixedHeight(90)
        form.addRow("账号邮箱", self.email_field)
        form.addRow("显示名称", self.name_field)
        form.addRow("兴趣爱好", self.interests_field)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存资料")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _choose_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择头像", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and (size.width() > 512 or size.height() > 512):
            reader.setScaledSize(size.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            QMessageBox.warning(self, "头像无法读取", "请选择有效的图片文件。")
            return
        self.pending_avatar = image
        self.avatar_button.setText("已选择新头像，保存后生效")

    def _save(self):
        profile = ProfileData(self.name_field.text().strip(),
                              self.interests_field.toPlainText().strip()[:1000])
        try:
            self.store.save(profile, self.pending_avatar)
        except OSError:
            QMessageBox.warning(self, "保存失败", "无法保存个人资料，请检查账号数据目录权限。")
            return
        self.saved.emit(profile)
        self.accept()
