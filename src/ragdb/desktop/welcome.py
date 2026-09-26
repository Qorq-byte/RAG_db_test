"""Native port of the supplied scroll-morph entrance, followed by explicit entry."""

from PySide6.QtCore import QAbstractAnimation, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsOpacityEffect, QLabel, QPushButton, QWidget

from ragdb.desktop.theme import ThemeManager
from ragdb.desktop.welcome_scene import MAX_SCROLL, WelcomeScene


class IntroTextEffect(QGraphicsBlurEffect):
    """Combine reference blur and fade in one effect (no nested Qt effects)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.alpha = 0.0

    def setOpacity(self, opacity):
        if self.alpha == opacity:
            return
        self.alpha = opacity
        self.setBlurRadius(10 * (1 - opacity))
        self.update()

    def draw(self, painter):
        if self.alpha <= 0:
            return
        painter.save()
        painter.setOpacity(painter.opacity() * self.alpha)
        super().draw(painter)
        painter.restore()


class WelcomePage(QWidget):
    enter_requested = Signal()

    def __init__(self, theme_manager: ThemeManager, parent=None, *, duration_ms: int = 4000) -> None:
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.setObjectName("welcomePage")
        self.setMinimumSize(640, 480)
        self.ready = self._started = self._busy = False
        self.scene = WelcomeScene(self)
        self.intro = QWidget(self)
        self.arc = QWidget(self)
        for layer in (self.intro, self.arc):
            layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.title = self._label("The future is built on AI.", self.intro)
        self.title.setWordWrap(True)
        self.subtitle = self._label("SCROLL TO EXPLORE", self.intro)
        self.arc_title = self._label("Explore Our Vision", self.arc)
        self.arc_description = self._label(
            "Discover a world where technology meets creativity.\n"
            "Scroll through our curated collection of innovations designed to shape the future.", self.arc)
        self.arc_description.setWordWrap(True)
        self.arc_description.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.intro_opacity = IntroTextEffect(self.intro)
        self.intro.setGraphicsEffect(self.intro_opacity)
        self.arc_opacity = QGraphicsOpacityEffect(self.arc)
        self.arc.setGraphicsEffect(self.arc_opacity)
        self.content = QWidget(self)
        self.enter_button = QPushButton("欢迎使用RAG系统", self.content)
        self.enter_button.setObjectName("welcomeEnter")
        self.enter_button.setAccessibleDescription("进入带侧边导航的知识工作台")
        self.enter_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.enter_button.setEnabled(False)
        self.enter_button.clicked.connect(self._enter)
        self.feedback = self._label("", self.content)
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
        self.animation.valueChanged.connect(self.scene.set_progress)
        self.animation.finished.connect(self.finish_intro)
        self.shortcuts = []
        for key, callback in (("Escape", self.finish_animation), ("End", self.finish_animation),
                              ("Home", lambda: self.scene.scroll_by(-MAX_SCROLL)),
                              ("Down", lambda: self.scene.scroll_by(120)),
                              ("Up", lambda: self.scene.scroll_by(-120)),
                              ("PgDown", lambda: self.scene.scroll_by(600)),
                              ("PgUp", lambda: self.scene.scroll_by(-600)),
                              ("Return", self._enter)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.scene.frame_changed.connect(self._update_content)
        self.theme_manager.changed.connect(self._apply_theme)
        self._apply_theme()
        self._update_content()

    @staticmethod
    def _label(text, parent):
        label = QLabel(text, parent)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _apply_theme(self, *_):
        # The reference explicitly uses a light canvas independently of workbench theme.
        self.scene.setBackgroundBrush(QColor("#fafafa"))
        self.setStyleSheet("""
            QWidget#welcomePage, QGraphicsView#welcomeScene { background: #fafafa; border: none; }
            QLabel { background: transparent; border: none; color: #1f2937; font-family: 'Segoe UI'; }
            QPushButton#welcomeEnter { background: #111827; color: white; border: 2px solid #111827;
                border-radius: 12px; font: 600 16px 'Microsoft YaHei UI'; }
            QPushButton#welcomeEnter:hover { background: #374151; }
            QPushButton#welcomeEnter:focus { border-color: #60a5fa; }
            QPushButton#welcomeEnter:disabled { background: #6b7280; border-color: #6b7280; }
        """)
        self.scene.set_reduce_motion(self.theme_manager.reduce_motion)
        if self.theme_manager.reduce_motion:
            self.finish_animation()

    def finish_intro(self):
        self.animation.stop()
        self.scene.set_progress(1.0)
        self._update_content()

    def finish_animation(self):
        """Keyboard / reduced-motion alternative to traversing the whole scroll range."""
        if self._busy:
            return
        self.animation.stop()
        self.scene.jump_to_end()
        if self.theme_manager.reduce_motion:
            self.reveal.stop()
            self.opacity.setOpacity(1.0)

    def _update_content(self):
        morph = self.scene.values[0]
        intro = max(0, min(1, (self.scene.progress - .625) / .25))
        self.intro_opacity.setOpacity(intro * max(0, 1 - morph * 2))
        self.arc_opacity.setOpacity(max(0, min(1, (morph - .8) / .2)))
        self.intro.move(0, self.height() // 2 - 48 + int(20 * (1 - intro)))
        self.arc.move(0, int(self.height() * .1 + 20 * (1 - max(0, min(1, (morph - .8) / .2)))))
        ready = (self.scene.progress >= 1 and self.scene.virtual_scroll >= MAX_SCROLL
                 and self.scene.values[1] >= .999 and (self.scene.settled or self.ready))
        if ready and not self.ready:
            self.ready = True
            self.content.show()
            self.content.raise_()
            self.enter_button.setEnabled(not self._busy)
            if self.theme_manager.reduce_motion:
                self.opacity.setOpacity(1)
            else:
                self.reveal.start()
            self.enter_button.setFocus(Qt.FocusReason.OtherFocusReason)
        elif not ready and self.ready and not self._busy:
            self.ready = False
            self.reveal.stop()
            self.content.hide()
            self.enter_button.setEnabled(False)

    def _enter(self):
        if not self.ready or self._busy:
            return
        self._busy = True
        self.scene.locked = True
        self.enter_button.setEnabled(False)
        self.feedback.setText("正在打开知识工作台…")
        self.enter_requested.emit()

    def show_error(self, message):
        self._busy = False
        self.scene.locked = False
        self.feedback.setText(message)
        self.enter_button.setEnabled(True)
        self.enter_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def wheelEvent(self, event):
        self.scene.wheelEvent(event)

    def _layout(self):
        w, h = self.width(), self.height()
        narrow = w < 768
        self.intro.setGeometry(0, h // 2 - 48, w, 140)
        inner_width = int(max(180, min(w - 32, min(w, h) * .7 - 100, 600)))
        self.title.setGeometry((w - inner_width) // 2, 0, inner_width, 76 if narrow else 54)
        self.title.setStyleSheet(f"font-size: {24 if narrow else 36}px; font-weight: 500;")
        self.subtitle.setGeometry(0, 90 if narrow else 66, w, 24)
        self.subtitle.setStyleSheet("font-size: 12px; font-weight: 700; letter-spacing: 2px; color: #9ca3af;")
        arc_y = int(h * .1 + 20 * (1 - max(0, min(1, (self.scene.values[0] - .8) / .2))))
        self.arc.setGeometry(0, arc_y, w, 180)
        self.arc_title.setGeometry(0, 0, w, 42 if narrow else 64)
        self.arc_title.setStyleSheet(f"font-size: {30 if narrow else 48}px; font-weight: 600; color: #111827;")
        description_width = min(512, w - 32)
        self.arc_description.setGeometry((w - description_width) // 2, 58 if narrow else 80, description_width, 92)
        self.arc_description.setStyleSheet(f"font-size: {14 if narrow else 16}px; color: #4b5563;")
        self.content.setGeometry((w - 360) // 2, h // 2 - 26, 360, 132)
        self.enter_button.setGeometry(25, 0, 310, 52)
        self.feedback.setGeometry(0, 66, 360, 60)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scene.setGeometry(self.rect())
        self._layout()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.ready:
            if self.animation.state() is QAbstractAnimation.State.Paused:
                self.animation.resume()
            elif not self._started and self.scene.progress < 1:
                self._started = True
                self.animation.start()

    def hideEvent(self, event):
        if self.animation.state() is QAbstractAnimation.State.Running:
            self.animation.pause()
        self.reveal.stop()
        self.opacity.setOpacity(1.0)
        self.scene.stop_hover_animations()
        super().hideEvent(event)
