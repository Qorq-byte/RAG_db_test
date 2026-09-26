"""The native entrance shown before the navigation workbench."""

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QPushButton, QWidget

from ragdb.desktop.theme import DARK, LIGHT, ThemeManager, ThemeMode
from ragdb.desktop.welcome_scene import WelcomeScene


class WelcomePage(QWidget):
    enter_requested = Signal()

    def __init__(self, theme_manager: ThemeManager, parent=None, *, duration_ms: int = 4000) -> None:
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.setObjectName("welcomePage")
        self.setMinimumSize(640, 480)
        self.ready = False
        self._started = False
        self.scene = WelcomeScene(self)
        self.brand = QLabel("RAG", self)
        self.brand.setObjectName("welcomeBrand")
        self.brand_caption = QLabel("个人知识工作台", self)
        self.brand_caption.setObjectName("welcomeCaption")
        self.skip_button = QPushButton("跳过动画  ↗", self)
        self.skip_button.setObjectName("welcomeSkip")
        self.skip_button.setAccessibleName("跳过开场动画")
        self.skip_button.setToolTip("跳过动画（Esc），随后点击欢迎按钮进入")
        self.skip_button.clicked.connect(self.finish_animation)
        self.footer = QLabel("本地资料  /  可追溯问答", self)
        self.footer.setObjectName("welcomeFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.content = QWidget(self)
        self.title = QLabel("让知识，产生连接。", self.content)
        self.title.setObjectName("welcomeTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel("检索 · 问答 · 学习", self.content)
        self.subtitle.setObjectName("welcomeSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.enter_button = QPushButton("欢迎使用RAG系统", self.content)
        self.enter_button.setObjectName("welcomeEnter")
        self.enter_button.setAccessibleName("欢迎使用RAG系统")
        self.enter_button.setAccessibleDescription("进入带侧边导航的知识工作台")
        self.enter_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.enter_button.setEnabled(False)
        self.enter_button.clicked.connect(self._enter)
        self.feedback = QLabel("点击进入你的知识工作台", self.content)
        self.feedback.setObjectName("welcomeFeedback")
        self.feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback.setWordWrap(True)
        self.content.hide()
        self.opacity = QGraphicsOpacityEffect(self.content)
        self.content.setGraphicsEffect(self.opacity)
        self.reveal = QVariantAnimation(self)
        self.reveal.setDuration(350)
        self.reveal.setStartValue(0.0)
        self.reveal.setEndValue(1.0)
        self.reveal.valueChanged.connect(self.opacity.setOpacity)

        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration_ms)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.animation.valueChanged.connect(self.scene.set_progress)
        self.animation.finished.connect(self.finish_animation)
        self.skip_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.skip_shortcut.activated.connect(self.finish_animation)
        self.enter_shortcut = QShortcut(QKeySequence("Return"), self)
        self.enter_shortcut.activated.connect(self._enter)
        self.theme_manager.changed.connect(self._apply_theme)
        self._apply_theme()

    def _apply_theme(self, *_):
        dark = self.theme_manager.resolved_mode() is ThemeMode.DARK
        colors = DARK if dark else LIGHT
        background = colors["window"] if dark else "#fafafa"
        self.scene.setBackgroundBrush(QColor(background))
        self.setStyleSheet(f"""
            QWidget#welcomePage {{ background: {background}; }}
            QGraphicsView#welcomeScene {{ background: {background}; border: none; }}
            QLabel {{ background: transparent; border: none; color: {colors['text']}; }}
            QLabel#welcomeBrand {{ font: 700 23px 'Segoe UI'; letter-spacing: 2px; }}
            QLabel#welcomeCaption, QLabel#welcomeSubtitle, QLabel#welcomeFooter,
            QLabel#welcomeFeedback {{ font-size: 13px; color: {colors['muted']}; }}
            QLabel#welcomeTitle {{ font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 30px; font-weight: 600; }}
            QPushButton#welcomeSkip {{ background: transparent; border: 1px solid transparent;
                color: {colors['muted']}; border-radius: 8px; font-size: 12px; padding: 6px; }}
            QPushButton#welcomeSkip:hover, QPushButton#welcomeSkip:focus {{ border-color: {colors['accent']}; }}
            QPushButton#welcomeEnter {{ background: {colors['accent']}; color: {'#071216' if dark else '#ffffff'};
                border: 2px solid {colors['accent']}; border-radius: 12px;
                font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 16px; font-weight: 600; padding: 8px; }}
            QPushButton#welcomeEnter:hover {{ background: {'#65d2e5' if dark else '#08748d'}; }}
            QPushButton#welcomeEnter:focus {{ border-color: {colors['text']}; }}
            QPushButton#welcomeEnter:disabled {{ background: {colors['raised']}; color: {colors['muted']}; border-color: {colors['border']}; }}
        """)
        self.scene.set_reduce_motion(self.theme_manager.reduce_motion)
        if self.theme_manager.reduce_motion:
            self.finish_animation()

    def finish_animation(self) -> None:
        if self.ready:
            if self.theme_manager.reduce_motion:
                self.reveal.stop()
                self.opacity.setOpacity(1.0)
            return
        self.animation.stop()
        self.scene.set_progress(1.0)
        self.ready = True
        self.skip_button.hide()
        self.skip_shortcut.setEnabled(False)
        self.enter_button.setEnabled(True)
        self.content.show()
        self.content.raise_()
        if self.theme_manager.reduce_motion:
            self.opacity.setOpacity(1.0)
        else:
            self.reveal.start()
        self.enter_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _enter(self) -> None:
        if not self.ready or not self.enter_button.isEnabled():
            return
        self.enter_button.setEnabled(False)
        self.feedback.setText("正在打开知识工作台…")
        self.enter_requested.emit()

    def show_error(self, message: str) -> None:
        self.feedback.setText(message)
        self.enter_button.setEnabled(True)
        self.enter_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width, height = self.width(), self.height()
        margin = 24 if width < 900 else 40
        self.scene.setGeometry(self.rect())
        self.brand.setGeometry(margin, 24, 72, 34)
        self.brand_caption.setGeometry(margin + 76, 29, 180, 26)
        self.skip_button.setGeometry(width - margin - 108, 24, 108, 34)
        self.footer.setGeometry(0, height - 47, width, 24)
        content_width = min(420, width - 120)
        self.content.setGeometry((width - content_width) // 2, height // 2 - 112, content_width, 220)
        self.title.setGeometry(0, 0, content_width, 48)
        self.title.setStyleSheet(f"font-size: {22 if width < 900 else 30}px;")
        self.subtitle.setGeometry(0, 51, content_width, 22)
        button_width = min(310, int(width * 0.44))
        self.enter_button.setGeometry((content_width - button_width) // 2, 86, button_width, 52)
        self.feedback.setGeometry((content_width - button_width) // 2, 151, button_width, 60)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.ready:
            if self.animation.state() is QAbstractAnimation.State.Paused:
                self.animation.resume()
            elif not self._started:
                self._started = True
                self.animation.start()

    def hideEvent(self, event) -> None:
        if self.animation.state() is QAbstractAnimation.State.Running:
            self.animation.pause()
        self.reveal.stop()
        self.opacity.setOpacity(1.0)
        self.scene.stop_hover_animations()
        super().hideEvent(event)
