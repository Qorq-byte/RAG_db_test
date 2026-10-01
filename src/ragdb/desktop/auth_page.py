"""Email-first account page displayed after the welcome animation."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ragdb.auth import AuthError, AuthService, AuthSession, PendingRegistration
from ragdb.config import AuthSettings
from ragdb.desktop.workers import BackgroundTask


class DotMap(QWidget):
    """Small, deterministic animated map inspired by the supplied design."""

    def __init__(self, *, reduce_motion: bool = False, parent=None):
        super().__init__(parent)
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self._advance)
        if not reduce_motion:
            self.timer.start()
        self.setMinimumHeight(225)

    def _advance(self):
        self.phase = (self.phase + 1) % 180
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        for x in range(10, w, 12):
            for y in range(12, h, 12):
                nx, ny = x / max(w, 1), y / max(h, 1)
                land = (
                    (.07 < nx < .27 and .14 < ny < .43) or
                    (.17 < nx < .30 and .45 < ny < .80) or
                    (.36 < nx < .51 and .20 < ny < .40) or
                    (.38 < nx < .54 and .42 < ny < .75) or
                    (.53 < nx < .85 and .17 < ny < .54) or
                    (.73 < nx < .89 and .67 < ny < .84)
                )
                if land and (x * 37 + y * 17) % 11 > 2:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(37, 99, 235, 65 + (x + y) % 55))
                    painter.drawEllipse(x, y, 2.4, 2.4)
        routes = [((.20, .32), (.43, .28)), ((.43, .28), (.70, .34)),
                  ((.24, .35), (.42, .57)), ((.70, .35), (.80, .73))]
        for index, (start, end) in enumerate(routes):
            sx, sy = start[0] * w, start[1] * h
            ex, ey = end[0] * w, end[1] * h
            painter.setPen(QPen(QColor(37, 99, 235, 95), 1.6))
            painter.drawLine(int(sx), int(sy), int(ex), int(ey))
            progress = ((self.phase + index * 39) % 180) / 180
            px, py = sx + (ex - sx) * progress, sy + (ey - sy) * progress
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(37, 99, 235, 180))
            painter.drawEllipse(int(px - 3), int(py - 3), 6, 6)


class AuthPage(QWidget):
    authenticated = Signal(object)

    def __init__(self, settings: AuthSettings, *, auth_factory: Callable = AuthService,
                 reduce_motion: bool = False, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.auth_factory = auth_factory
        self.pending: PendingRegistration | None = None
        self._task = None
        self._mode = "login"
        self._email = ""
        self._steps = []
        self.setObjectName("authPage")
        self.setMinimumSize(640, 480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 36, 36, 36)
        card = QFrame()
        self.card = card
        card.setObjectName("authCard")
        card.setMaximumWidth(1060)
        card.setMinimumHeight(570)
        outer.addStretch(1)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        columns = QHBoxLayout(card)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)

        self.story = QFrame()
        self.story.setObjectName("authStory")
        self.story.setMinimumWidth(270)
        left = QVBoxLayout(self.story)
        left.setContentsMargins(38, 38, 38, 34)
        brand = QLabel("◈  RAG DB")
        brand.setObjectName("authBrand")
        left.addWidget(brand)
        left.addStretch()
        self.map = DotMap(reduce_motion=reduce_motion)
        left.addWidget(self.map)
        hero = QLabel("让知识，随时可达。")
        hero.setObjectName("authHero")
        left.addWidget(hero)
        intro = QLabel("连接你的资料与思考，开启专属知识工作台。")
        intro.setWordWrap(True)
        intro.setObjectName("authIntro")
        left.addWidget(intro)
        left.addStretch()
        columns.addWidget(self.story, 1)

        form_panel = QFrame()
        form_panel.setObjectName("authForm")
        form_panel.setMinimumWidth(320)
        columns.addWidget(form_panel, 1)
        form = QVBoxLayout(form_panel)
        form.setContentsMargins(42, 38, 42, 30)
        form.setSpacing(12)
        tabs = QHBoxLayout()
        self.login_tab = QPushButton("登录")
        self.register_tab = QPushButton("注册")
        for button in (self.login_tab, self.register_tab):
            button.setObjectName("authTab")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            tabs.addWidget(button)
        tabs.addStretch()
        form.addLayout(tabs)
        form.addStretch(1)
        self.title = QLabel("欢迎回来")
        self.title.setObjectName("authTitle")
        form.addWidget(self.title)
        self.description = QLabel("登录后继续使用你的知识库")
        self.description.setObjectName("authDescription")
        self.description.setWordWrap(True)
        form.addWidget(self.description)
        form.addSpacing(12)

        self.stack = QStackedWidget()
        form.addWidget(self.stack)
        self.login_email = self._field("邮箱地址", "you@example.com")
        self.login_password = self._field("密码", "请输入密码", password=True)
        self.login_eye = self._eye(self.login_password)
        self.login_button = self._primary("登录并进入工作台")
        self.restore_button = QPushButton("继续使用本机已登录账号")
        self.restore_button.setObjectName("authLink")
        self.forgot_button = QPushButton("忘记密码？用邮箱验证码重新设置")
        self.forgot_button.setObjectName("authLink")
        login = self._step()
        for widget in (self._label("邮箱"), self.login_email, self._label("密码"),
                       self.login_password, self.login_eye, self.login_button,
                       self.restore_button, self.forgot_button):
            login.addWidget(widget)
        self.stack.addWidget(login.parentWidget())

        self.register_email = self._field("邮箱地址", "you@example.com")
        self.send_button = self._primary("获取邮箱验证码")
        email_step = self._step()
        for widget in (self._label("邮箱"), self.register_email, self.send_button):
            email_step.addWidget(widget)
        self.stack.addWidget(email_step.parentWidget())

        self.code = self._field("邮箱验证码", "输入邮件中的完整数字验证码")
        self.code.setMaxLength(32)
        self.code.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
        self.verify_button = self._primary("验证邮箱")
        self.resend_button = QPushButton("重新发送验证码")
        self.resend_button.setObjectName("authLink")
        self.back_email = QPushButton("修改邮箱地址")
        self.back_email.setObjectName("authLink")
        code_step = self._step()
        for widget in (self._label("验证码"), self.code, self.verify_button,
                       self.resend_button, self.back_email):
            code_step.addWidget(widget)
        self.stack.addWidget(code_step.parentWidget())

        self.new_password = self._field("设置密码", "至少 8 位", password=True)
        self.confirm_password = self._field("确认密码", "再次输入密码", password=True)
        self.new_eye = self._eye(self.new_password)
        self.save_password_button = self._primary("设置密码并完成注册")
        password_step = self._step()
        for widget in (self._label("设置密码"), self.new_password, self.new_eye,
                       self._label("确认密码"), self.confirm_password,
                       self.save_password_button):
            password_step.addWidget(widget)
        self.stack.addWidget(password_step.parentWidget())

        form.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("authStatus")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(36)
        form.addWidget(self.status)
        self.login_tab.clicked.connect(lambda: self._switch("login"))
        self.register_tab.clicked.connect(lambda: self._switch("register"))
        self.login_button.clicked.connect(self._login)
        self.restore_button.clicked.connect(lambda: self._run("restore"))
        self.forgot_button.clicked.connect(self._recover)
        self.send_button.clicked.connect(self._send)
        self.verify_button.clicked.connect(self._verify)
        self.resend_button.clicked.connect(self._resend)
        self.back_email.clicked.connect(lambda: self._show_step(1))
        self.save_password_button.clicked.connect(self._save_password)
        self.login_password.returnPressed.connect(self._login)
        self.register_email.returnPressed.connect(self._send)
        self.code.returnPressed.connect(self._verify)
        self.confirm_password.returnPressed.connect(self._save_password)
        self._switch("login")
        self.setStyleSheet("""
            QWidget#authPage { background: #eef3ff; font-family: 'Microsoft YaHei UI'; }
            QFrame#authCard { background: white; border: 1px solid #dfe7f6; border-radius: 20px; }
            QFrame#authStory { background: #e4edff; border: none; border-radius: 20px; }
            QFrame#authForm { background: white; border: none; border-radius: 20px; }
            QLabel { background: transparent; color: #20304c; }
            QLabel#authBrand { color: #2455b6; font-size: 19px; font-weight: 800; }
            QLabel#authHero { color: #173b83; font-size: 27px; font-weight: 750; }
            QLabel#authIntro, QLabel#authDescription { color: #63718c; font-size: 13px; }
            QLabel#authTitle { color: #17294d; font-size: 29px; font-weight: 750; }
            QLabel#authStatus { color: #3559a7; font-size: 12px; }
            QLineEdit { background: #f8faff; border: 1px solid #d8e2f2; border-radius: 9px;
                color: #17294d; padding: 10px 13px; min-height: 23px; font-size: 13px; }
            QLineEdit:focus { border: 2px solid #4f78df; }
            QPushButton#authPrimary { border: none; border-radius: 9px; background: #345cce;
                color: white; padding: 12px; font-size: 14px; font-weight: 700; }
            QPushButton#authPrimary:hover { background: #2749b7; }
            QPushButton#authPrimary:disabled { background: #9daed5; }
            QPushButton#authLink, QPushButton#authTab, QPushButton#authEye { border: none;
                background: transparent; color: #345cce; padding: 6px; text-align: left; }
            QPushButton#authTab { font-size: 14px; font-weight: 700; color: #74829d; }
            QPushButton#authTab[active="true"] { color: #244dbf; border-bottom: 2px solid #345cce; }
        """)

    @staticmethod
    def _field(name, placeholder, *, password=False):
        field = QLineEdit()
        field.setAccessibleName(name)
        field.setPlaceholderText(placeholder)
        if password:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    @staticmethod
    def _label(text):
        label = QLabel(text)
        label.setStyleSheet("font-weight: 650; font-size: 12px;")
        return label

    @staticmethod
    def _primary(text):
        button = QPushButton(text)
        button.setObjectName("authPrimary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _step(self):
        widget = QWidget()
        self._steps.append(widget)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        return layout

    @staticmethod
    def _eye(field):
        button = QPushButton("显示密码")
        button.setObjectName("authEye")
        button.setAccessibleName("显示或隐藏密码")

        def toggle():
            visible = field.echoMode() == QLineEdit.EchoMode.Password
            field.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
            button.setText("隐藏密码" if visible else "显示密码")

        button.clicked.connect(toggle)
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.card.setFixedWidth(min(1060, max(320, self.width() - 72)))
        self.story.setVisible(self.width() >= 850)

    def _switch(self, mode, *, force=False):
        if self._task is not None and not force:
            return
        self._mode = mode
        self.pending = None
        self._show_step(0 if mode == "login" else 1)
        self.status.clear()
        for button, active in ((self.login_tab, mode == "login"),
                               (self.register_tab, mode == "register")):
            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)

    def _show_step(self, step):
        self.stack.setCurrentIndex(step)
        titles = {0: ("欢迎回来", "登录后继续使用你的知识库"),
                  1: ("创建账号", "先填写邮箱，获取验证码"),
                  2: ("验证邮箱", f"请输入发往 {self._email} 的完整验证码"),
                  3: ("设置密码", "邮箱已验证，设置密码后即可登录")}
        title, description = titles[step]
        self.title.setText(title)
        self.description.setText(description)

    def _recover(self):
        self.register_email.setText(self.login_email.text())
        self._switch("register")
        self.status.setText("输入邮箱验证码后可以重新设置密码。")

    def _run(self, mode, *, email="", code="", password="", pending=None):
        if self._task is not None:
            return
        self.status.setText("正在联系认证服务…")
        for button in (self.login_button, self.restore_button, self.send_button,
                       self.verify_button, self.resend_button, self.save_password_button):
            button.setEnabled(False)

        def request():
            try:
                auth = self.auth_factory(self.settings)
                try:
                    if mode in ("send", "resend"):
                        return auth.request_email_code(email)
                    if mode == "verify":
                        return auth.verify_email_code(email, code)
                    if mode == "password":
                        return auth.set_registration_password(pending, password)
                    if mode == "login":
                        return auth.sign_in(email, password)
                    return auth.restore()
                finally:
                    auth.close()
            except AuthError:
                raise
            except Exception:
                raise AuthError("认证操作失败，请稍后重试。") from None

        self._task = BackgroundTask(mode, request)
        self._task.signals.succeeded.connect(self._succeeded)
        self._task.signals.failed.connect(self._failed)
        self._task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self._task)

    def _send(self):
        self._email = self.register_email.text().strip()
        self._run("send", email=self._email)

    def _resend(self):
        self._run("resend", email=self._email)

    def _verify(self):
        self._run("verify", email=self._email, code=self.code.text())

    def _save_password(self):
        password = self.new_password.text()
        if password != self.confirm_password.text():
            self.status.setText("两次输入的密码不一致。")
        elif self.pending is None:
            self.status.setText("请先验证邮箱。")
        else:
            self._run("password", password=password, pending=self.pending)

    def _login(self):
        self._run("login", email=self.login_email.text(), password=self.login_password.text())

    @Slot(object, object)
    def _succeeded(self, mode, result):
        if mode in ("send", "resend"):
            self.pending = None
            self.code.clear()
            self._show_step(2)
            self.status.setText("验证码邮件已发送。请查看收件箱和垃圾邮件，并输入完整验证码。")
            self.code.setFocus()
        elif mode == "verify":
            self.pending = result
            self.code.clear()
            self._show_step(3)
            self.status.setText("邮箱验证成功，请设置密码。")
            self.new_password.setFocus()
        elif mode == "password":
            self.pending = None
            self.new_password.clear()
            self.confirm_password.clear()
            self.login_email.setText(self._email)
            self._switch("login", force=True)
            self.status.setText("账号已准备好，请输入刚设置的密码登录。")
            self.login_password.setFocus()
        else:
            self.authenticated.emit(result)

    @Slot(object, str)
    def _failed(self, _mode, error):
        self.status.setText(error)

    @Slot(object)
    def _finished(self, _mode):
        self._task = None
        for button in (self.login_button, self.restore_button, self.send_button,
                       self.verify_button, self.resend_button, self.save_password_button):
            button.setEnabled(True)

    def show_error(self, message):
        self.status.setText(message)

    @property
    def busy(self):
        return self._task is not None
