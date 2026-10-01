"""Private, per-account desktop profile and its sidebar control."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout,
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
        self.setObjectName("profileTrigger")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(68)
        self.setAccessibleName("打开个人资料菜单")
        self.setToolTip("个人资料、模型和设置")

    def set_profile(self, profile: ProfileData, email: str, avatar: QPixmap):
        self.name = profile.name.strip() or (email.split("@", 1)[0] if email else "个人账号")
        self.email = email
        self.avatar = avatar
        self.update()

    def set_collapsed(self, collapsed: bool):
        self.collapsed = collapsed
        self.setFixedHeight(48 if collapsed else 68)
        self.update()

    def set_dark_mode(self, dark: bool):
        self.dark = dark
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse() or self.hasFocus()
        surface = QColor("#263342" if self.dark else "#ffffff")
        border = QColor("#52758d" if hovered and self.dark else
                        "#8ac2d0" if hovered else "#364456" if self.dark else "#d9e3ec")
        painter.setBrush(surface)
        painter.setPen(border)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)
        avatar_size = 34
        avatar_x = (self.width() - avatar_size) // 2 if self.collapsed else self.width() - avatar_size - 11
        avatar_y = (self.height() - avatar_size) // 2
        avatar_rect = QRectF(avatar_x, avatar_y, avatar_size, avatar_size)
        gradient = QColor("#6958c7" if self.dark else "#5572d7")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(avatar_rect)
        if not self.avatar.isNull():
            path = QPainterPath()
            path.addEllipse(avatar_rect.adjusted(2, 2, -2, -2))
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(avatar_rect.toRect(), self.avatar)
            painter.restore()
        else:
            painter.setPen(QColor("#ffffff"))
            font = QFont("Microsoft YaHei UI", 11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(avatar_rect, Qt.AlignmentFlag.AlignCenter, self.name[:1].upper())
        if not self.collapsed:
            name_font = QFont("Microsoft YaHei UI", 10)
            name_font.setBold(True)
            painter.setFont(name_font)
            painter.setPen(QColor("#e8edf4" if self.dark else "#18202b"))
            available = max(30, avatar_x - 23)
            painter.drawText(12, 14, available, 18, Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideRight, available))
            painter.setPen(QColor("#a3b0c1" if self.dark else "#687386"))
            painter.setFont(QFont("Microsoft YaHei UI", 8))
            painter.drawText(12, 36, available, 17, Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(self.email, Qt.TextElideMode.ElideRight, available))


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
