"""Email verification gate shown before opening the desktop workbench."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QTimer, Slot
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ragdb.auth import AuthError, AuthService, AuthSession
from ragdb.config import AuthSettings
from ragdb.desktop.workers import BackgroundTask


class AuthDialog(QDialog):
    def __init__(self, settings: AuthSettings, *, auth_factory: Callable[[AuthSettings], AuthService] = AuthService,
                 restore_on_open: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("RAG DB · 邮箱账号")
        self.setMinimumWidth(460)
        self.settings = settings
        self.auth_factory = auth_factory
        self.session: AuthSession | None = None
        self._task = None
        title = QLabel("登录知识库")
        title.setStyleSheet("font-size: 23px; font-weight: 700")
        description = QLabel("请先注册，在邮箱中查看验证码并在这里验证，然后登录使用桌面工作台。")
        description.setWordWrap(True)
        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")
        self.email.setAccessibleName("邮箱")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName("密码")
        self.password.setPlaceholderText("至少 8 位")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setAccessibleName("确认密码，仅注册时填写")
        self.code = QLineEdit()
        self.code.setMaxLength(32)
        self.code.setPlaceholderText("邮件中的数字验证码")
        self.code.setAccessibleName("邮箱验证码")
        form = QFormLayout()
        form.addRow("邮箱", self.email)
        form.addRow("密码", self.password)
        form.addRow("确认密码", self.confirm)
        form.addRow("验证码", self.code)
        self.status = QLabel("注册后请查收验证码邮件。")
        self.status.setWordWrap(True)
        self.register_button = QPushButton("注册并发送验证码")
        self.login_button = QPushButton("登录")
        self.verify_button = QPushButton("验证邮箱")
        self.resend_button = QPushButton("重发验证码")
        self.login_button.setDefault(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.register_button)
        buttons.addWidget(self.login_button)
        verification_buttons = QHBoxLayout()
        verification_buttons.addWidget(self.verify_button)
        verification_buttons.addWidget(self.resend_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        layout.addLayout(verification_buttons)
        self.register_button.clicked.connect(self._register)
        self.login_button.clicked.connect(self._login)
        self.verify_button.clicked.connect(self._verify)
        self.resend_button.clicked.connect(self._resend)
        if restore_on_open:
            QTimer.singleShot(0, self._restore)

    def _run(self, mode: str, email: str = "", password: str = "", code: str = "") -> None:
        if self._task is not None:
            return
        self.status.setText("正在联系认证服务…")
        self.login_button.setEnabled(False)
        self.register_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.resend_button.setEnabled(False)

        def request():
            try:
                auth = self.auth_factory(self.settings)
                try:
                    if mode == "register":
                        auth.sign_up(email, password)
                        return None
                    if mode == "verify":
                        auth.verify_email_code(email, code)
                        return None
                    if mode == "resend":
                        auth.resend_confirmation(email)
                        return None
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

    @Slot()
    def _register(self) -> None:
        if self.password.text() != self.confirm.text():
            self.status.setText("两次输入的密码不一致。")
            return
        self._run("register", self.email.text(), self.password.text())

    @Slot()
    def _login(self) -> None:
        self._run("login", self.email.text(), self.password.text())

    @Slot()
    def _verify(self) -> None:
        self._run("verify", self.email.text(), code=self.code.text())

    @Slot()
    def _resend(self) -> None:
        self._run("resend", self.email.text())

    def _restore(self) -> None:
        if self.settings.url and self.settings.publishable_key:
            self._run("restore")
        else:
            self.status.setText("认证服务尚未配置。请设置 auth.url 和 auth.publishable_key 后重新启动。")

    @Slot(object, object)
    def _succeeded(self, mode, result) -> None:
        if mode == "register":
            self.status.setText("如邮箱可注册，验证码邮件已发送。请输入邮件中的数字验证码。")
            self.password.clear()
            self.confirm.clear()
            self.code.setFocus()
            return
        if mode == "verify":
            self.status.setText("邮箱验证成功。请输入邮箱和密码登录。")
            self.code.clear()
            self.password.clear()
            self.confirm.clear()
            return
        if mode == "resend":
            self.status.setText("如邮箱尚未验证，新的验证码已发送。请使用最新邮件中的验证码。")
            return
        self.session = result
        self.accept()

    @Slot(object, str)
    def _failed(self, mode, error: str) -> None:
        if mode == "restore" and "请先登录" in error:
            self.status.setText("请输入已验证的邮箱账号和密码。")
        else:
            self.status.setText(error)

    @Slot(object)
    def _finished(self, _mode) -> None:
        self._task = None
        self.login_button.setEnabled(True)
        self.register_button.setEnabled(True)
        self.verify_button.setEnabled(True)
        self.resend_button.setEnabled(True)

    def reject(self) -> None:
        if self._task is not None:
            self.status.setText("请等待当前认证请求完成。")
            return
        super().reject()
