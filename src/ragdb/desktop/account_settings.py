"""Account preferences and email-verified password recovery."""

from __future__ import annotations

from collections.abc import Callable
import re

from PySide6.QtCore import QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ragdb.auth import AuthError, AuthService, PendingRegistration
from ragdb.config import AuthSettings
from ragdb.desktop.theme_switcher import ThemeSwitcher
from ragdb.desktop.workers import BackgroundTask


class PasswordRecoveryDialog(QDialog):
    """Verify the current account's email before accepting a new password."""

    def __init__(self, settings: AuthSettings, email: str, parent=None,
                 *, auth_factory: Callable = AuthService):
        super().__init__(parent)
        self.settings = settings
        self.email = email
        self.auth_factory = auth_factory
        self.pending: PendingRegistration | None = None
        self._task = None
        self.setWindowTitle("找回密码")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(13)
        title = QLabel("用邮箱验证码重设密码")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        root.addWidget(title)
        self.description = QLabel(f"验证码将发送到 {email}")
        self.description.setWordWrap(True)
        root.addWidget(self.description)
        self.steps = QStackedWidget()
        root.addWidget(self.steps)

        first = QWidget()
        first_layout = QVBoxLayout(first)
        first_layout.setContentsMargins(0, 0, 0, 0)
        self.send_button = QPushButton("发送验证码")
        first_layout.addWidget(self.send_button)
        self.steps.addWidget(first)

        second = QWidget()
        second_layout = QVBoxLayout(second)
        second_layout.setContentsMargins(0, 0, 0, 0)
        self.code = QLineEdit()
        self.code.setAccessibleName("邮箱验证码")
        self.code.setMaxLength(32)
        self.code.setPlaceholderText("请输入邮件中的完整数字验证码")
        self.verify_button = QPushButton("验证邮箱")
        self.resend_button = QPushButton("重新发送验证码")
        second_layout.addWidget(self.code)
        second_layout.addWidget(self.verify_button)
        second_layout.addWidget(self.resend_button)
        self.steps.addWidget(second)

        third = QWidget()
        third_layout = QVBoxLayout(third)
        third_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("至少 8 位")
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("新密码", self.password)
        form.addRow("确认密码", self.confirm)
        third_layout.addLayout(form)
        self.save_button = QPushButton("设置新密码")
        third_layout.addWidget(self.save_button)
        self.steps.addWidget(third)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(30)
        root.addWidget(self.status)
        self.send_button.clicked.connect(lambda: self._run("send"))
        self.resend_button.clicked.connect(lambda: self._run("resend"))
        self.verify_button.clicked.connect(lambda: self._run("verify", code=self.code.text()))
        self.save_button.clicked.connect(self._save_password)
        self.code.returnPressed.connect(lambda: self._run("verify", code=self.code.text()))
        self.confirm.returnPressed.connect(self._save_password)

    def _save_password(self):
        if self.pending is None:
            self.status.setText("请先验证邮箱。")
        elif self.password.text() != self.confirm.text():
            self.status.setText("两次输入的密码不一致。")
        else:
            self._run("password", password=self.password.text(), pending=self.pending)

    def _run(self, mode, *, code="", password="", pending=None):
        if self._task is not None:
            return
        self.status.setText("正在联系认证服务…")
        for button in (self.send_button, self.resend_button, self.verify_button, self.save_button):
            button.setEnabled(False)

        def request():
            try:
                auth = self.auth_factory(self.settings)
                try:
                    if mode in ("send", "resend"):
                        return auth.request_email_code(self.email)
                    if mode == "verify":
                        return auth.verify_email_code(self.email, code)
                    return auth.set_registration_password(pending, password)
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

    @Slot(object, object)
    def _succeeded(self, mode, result):
        if mode in ("send", "resend"):
            self.pending = None
            self.code.clear()
            self.steps.setCurrentIndex(1)
            self.status.setText("验证码已发送，请查看邮箱并输入完整验证码。")
            self.code.setFocus()
        elif mode == "verify":
            self.pending = result
            self.code.clear()
            self.steps.setCurrentIndex(2)
            self.status.setText("邮箱已验证，请设置新密码。")
            self.password.setFocus()
        else:
            self.pending = None
            self.password.clear()
            self.confirm.clear()
            self.accept()

    @Slot(object, str)
    def _failed(self, _mode, error):
        self.status.setText(error)

    @Slot(object)
    def _finished(self, _mode):
        self._task = None
        for button in (self.send_button, self.resend_button, self.verify_button, self.save_button):
            button.setEnabled(True)

    def reject(self):
        if self._task is not None:
            self.status.setText("请等待当前请求完成。")
            return
        super().reject()


class AccountSettingsDialog(QDialog):
    logout_requested = Signal()
    delete_requested = Signal(str)

    def __init__(self, manager, email: str, auth_settings: AuthSettings | None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.email = email
        self.auth_settings = auth_settings
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(15)
        title = QLabel("设置")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(QLabel("界面主题"))
        self.theme = ThemeSwitcher(manager)
        layout.addWidget(self.theme)
        self.reduce_motion = QCheckBox("减少动效")
        self.reduce_motion.setChecked(manager.reduce_motion)
        self.reduce_motion.toggled.connect(manager.set_reduce_motion)
        layout.addWidget(self.reduce_motion)
        layout.addSpacing(8)
        self.recover_button = QPushButton("用邮箱验证码找回密码")
        self.recover_button.setEnabled(auth_settings is not None and bool(email))
        self.recover_button.clicked.connect(self._recover)
        layout.addWidget(self.recover_button)
        self.logout_button = QPushButton("退出登录")
        self.logout_button.setProperty("danger", True)
        self.logout_button.clicked.connect(self._logout)
        layout.addWidget(self.logout_button)
        self.delete_button = QPushButton("永久注销账号并删除本机资料")
        self.delete_button.setProperty("danger", True)
        self.delete_button.setEnabled(auth_settings is not None and bool(email))
        self.delete_button.clicked.connect(self._delete_account)
        layout.addWidget(self.delete_button)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        layout.addLayout(close_row)

    def _recover(self):
        dialog = PasswordRecoveryDialog(self.auth_settings, self.email, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.accept()
            self.logout_requested.emit()

    def _logout(self):
        self.accept()
        self.logout_requested.emit()

    def _delete_account(self):
        dialog = DeleteAccountDialog(self.auth_settings, self.email, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.accept()
            self.delete_requested.emit(dialog.code_value)


class DeleteAccountDialog(QDialog):
    """Deliberate local confirmation before the server verifies a fresh OTP."""

    PHRASE = "永久删除"

    def __init__(self, settings: AuthSettings, email: str, parent=None,
                 *, auth_factory: Callable = AuthService):
        super().__init__(parent)
        self.settings = settings
        self.email = email
        self.auth_factory = auth_factory
        self.code_value = ""
        self._task = None
        self.setWindowTitle("永久注销账号")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(12)
        title = QLabel("永久注销账号")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)
        warning = QLabel(
            f"将永久删除 {email} 的 Supabase 账号和这个账号在本机的知识库、会话与个人资料。"
            "操作无法撤销，其他账号的本机资料不会删除。"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.send_button = QPushButton("发送注销验证码")
        self.send_button.clicked.connect(self._send)
        layout.addWidget(self.send_button)
        form = QFormLayout()
        self.code = QLineEdit()
        self.code.setAccessibleName("注销邮箱验证码")
        self.code.setMaxLength(32)
        self.code.setPlaceholderText("邮件中的完整数字验证码")
        self.code.setEnabled(False)
        self.confirm = QLineEdit()
        self.confirm.setPlaceholderText(self.PHRASE)
        self.confirm.setEnabled(False)
        form.addRow("邮箱验证码", self.code)
        form.addRow(f"输入“{self.PHRASE}”", self.confirm)
        layout.addLayout(form)
        self.status = QLabel("先发送验证码，确认邮箱归属。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.delete_button = QPushButton("永久删除账号及本机资料")
        self.delete_button.setProperty("danger", True)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._confirm)
        buttons.addWidget(cancel)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)

    def _send(self):
        if self._task is not None:
            return
        self.send_button.setEnabled(False)
        self.status.setText("正在发送验证码…")

        def request():
            auth = self.auth_factory(self.settings)
            try:
                auth.request_email_code(self.email)
            finally:
                auth.close()

        self._task = BackgroundTask("delete-code", request)
        self._task.signals.succeeded.connect(self._sent)
        self._task.signals.failed.connect(self._failed)
        self._task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self._task)

    @Slot(object, object)
    def _sent(self, _mode, _result):
        self.code.clear()
        self.code.setEnabled(True)
        self.confirm.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.status.setText("验证码已发送。输入完整验证码和确认文字后才能永久删除。")
        self.code.setFocus()

    @Slot(object, str)
    def _failed(self, _mode, error):
        self.status.setText(error)

    @Slot(object)
    def _finished(self, _mode):
        self._task = None
        self.send_button.setEnabled(True)

    def _confirm(self):
        code = self.code.text().strip()
        if not re.fullmatch(r"[0-9]{6,32}", code):
            self.status.setText("请输入邮件中的完整数字验证码。")
            return
        if self.confirm.text().strip() != self.PHRASE:
            self.status.setText(f"请输入“{self.PHRASE}”确认永久删除。")
            return
        self.code_value = code
        self.accept()

    def reject(self):
        if self._task is not None:
            self.status.setText("请等待验证码发送完成。")
            return
        super().reject()
