"""The profile menu routes to real account features and isolates local data."""

import os
import time
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from ragdb.auth import PendingRegistration
from ragdb.config import AuthSettings
from ragdb.desktop.account_settings import AccountSettingsDialog, DeleteAccountDialog, PasswordRecoveryDialog
from ragdb.desktop.profile import ProfileData, ProfileStore
from ragdb.desktop.theme import ThemeManager
from ragdb.desktop.window import MainWindow


APP = QApplication.instance() or QApplication([])
AUTH = AuthSettings(url="https://example.supabase.co", publishable_key="sb_publishable_test")


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        QTest.qWait(5)
    APP.processEvents()
    assert predicate()


def test_profile_fields_and_avatar_are_private_to_each_account(tmp_path):
    first = ProfileStore(tmp_path / "accounts" / "first")
    second = ProfileStore(tmp_path / "accounts" / "second")
    avatar = QImage(32, 32, QImage.Format.Format_ARGB32)
    avatar.fill(QColor("#2974bb"))
    first.save(ProfileData("小明", "阅读、机器学习"), avatar)
    assert first.load() == ProfileData("小明", "阅读、机器学习")
    assert not first.avatar().isNull()
    assert second.load() == ProfileData()
    assert second.avatar().isNull()


def test_sidebar_profile_menu_opens_existing_model_page_and_logout():
    window = MainWindow()
    window.show()
    APP.processEvents()
    assert window.navigation.profile_button.isVisible()
    assert all(button.label != "模型设置" for button in window.navigation.buttons)
    window.model_action.trigger()
    assert window.pages.currentIndex() == 6
    emitted = []
    window.logout_requested.connect(lambda: emitted.append(True))
    window.signout_action.trigger()
    assert emitted == [True]
    window.close()


def test_settings_change_theme_and_emit_logout(tmp_path):
    manager = ThemeManager(QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat))
    dialog = AccountSettingsDialog(manager, "a@example.com", AUTH)
    dialog.theme.buttons[next(mode for mode in dialog.theme.buttons if mode.value == "dark")].click()
    assert manager.mode.value == "dark"
    dialog.reduce_motion.setChecked(True)
    assert manager.reduce_motion
    events = []
    dialog.logout_requested.connect(lambda: events.append("logout"))
    dialog.logout_button.click()
    assert events == ["logout"]


def test_password_recovery_verifies_email_before_setting_password():
    calls = []
    pending = PendingRegistration(UUID("adad7c76-3f69-4c47-a9bb-1b03fef6653c"),
                                  "a@example.com", "temporary", 2**31)

    class FakeAuth:
        def __init__(self, _settings):
            pass

        def request_email_code(self, email):
            calls.append(("send", email))

        def verify_email_code(self, email, code):
            calls.append(("verify", email, code))
            return pending

        def set_registration_password(self, checked, password):
            calls.append(("password", checked.email, password))

        def close(self):
            pass

    dialog = PasswordRecoveryDialog(AUTH, "a@example.com", auth_factory=FakeAuth)
    assert dialog.steps.currentIndex() == 0
    dialog.send_button.click()
    wait_until(lambda: dialog.steps.currentIndex() == 1)
    dialog.code.setText("12345678")
    dialog.verify_button.click()
    wait_until(lambda: dialog.steps.currentIndex() == 2)
    wait_until(lambda: dialog._task is None)
    dialog.password.setText("abcdefgh")
    dialog.confirm.setText("abcdefgh")
    dialog.save_button.click()
    wait_until(lambda: dialog.result() == QDialog.DialogCode.Accepted)
    assert calls == [("send", "a@example.com"), ("verify", "a@example.com", "12345678"),
                     ("password", "a@example.com", "abcdefgh")]


def test_permanent_deletion_needs_fresh_code_and_exact_confirmation():
    sent = []

    class FakeAuth:
        def __init__(self, _settings):
            pass

        def request_email_code(self, email):
            sent.append(email)

        def close(self):
            pass

    dialog = DeleteAccountDialog(AUTH, "a@example.com", auth_factory=FakeAuth)
    assert not dialog.delete_button.isEnabled()
    dialog.send_button.click()
    wait_until(lambda: dialog.delete_button.isEnabled())
    dialog.code.setText("12345678")
    dialog.confirm.setText("删除")
    dialog.delete_button.click()
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.confirm.setText("永久删除")
    dialog.delete_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.code_value == "12345678"
    assert sent == ["a@example.com"]
