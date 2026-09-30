"""The desktop login window must wait for a verified server session."""

import os
import time
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from ragdb.auth import AuthError, AuthSession
from ragdb.config import AuthSettings
from ragdb.desktop.auth_dialog import AuthDialog


APPLICATION = QApplication.instance() or QApplication([])
SETTINGS = AuthSettings(url="https://example.supabase.co", publishable_key="sb_publishable_test")


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        APPLICATION.processEvents()
        QTest.qWait(5)
    APPLICATION.processEvents()
    assert predicate()


def test_registration_shows_email_confirmation_and_does_not_open_workbench():
    calls = []

    class FakeAuth:
        def __init__(self, _settings):
            pass

        def sign_up(self, email, password):
            calls.append((email, password))

        def close(self):
            pass

    dialog = AuthDialog(SETTINGS, auth_factory=FakeAuth, restore_on_open=False)
    dialog.email.setText("a@example.com")
    dialog.password.setText("abcdefgh")
    dialog.confirm.setText("abcdefgh")
    dialog._register()
    wait_until(lambda: "验证邮件已发送" in dialog.status.text())
    assert calls == [("a@example.com", "abcdefgh")]
    assert dialog.session is None
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.close()


def test_login_only_accepts_verified_session():
    session = AuthSession(UUID("adad7c76-3f69-4c47-a9bb-1b03fef6653c"), "a@example.com", "access", "refresh", 2**31)

    class FakeAuth:
        def __init__(self, _settings):
            pass

        def sign_in(self, email, password):
            if password == "unverified":
                raise AuthError("请先完成邮箱确认。")
            return session

        def close(self):
            pass

    dialog = AuthDialog(SETTINGS, auth_factory=FakeAuth, restore_on_open=False)
    dialog.email.setText("a@example.com")
    dialog.password.setText("unverified")
    dialog._login()
    wait_until(lambda: "邮箱确认" in dialog.status.text())
    assert dialog.result() != QDialog.DialogCode.Accepted
    dialog.password.setText("abcdefgh")
    dialog._login()
    wait_until(lambda: dialog.result() == QDialog.DialogCode.Accepted)
    assert dialog.session == session


def test_desktop_entry_never_constructs_workbench_without_login(monkeypatch):
    from ragdb.config import AppSettings
    import ragdb.desktop.app as desktop_app

    class RejectedDialog:
        session = None

        def __init__(self, _settings):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(desktop_app, "load_settings", lambda **_: AppSettings())
    monkeypatch.setattr(desktop_app, "AuthDialog", RejectedDialog)
    monkeypatch.setattr(desktop_app, "WelcomeWindow", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("workbench opened")))
    assert desktop_app.main() == 0


def test_desktop_entry_keeps_event_loop_alive_after_successful_login(monkeypatch):
    from ragdb.config import AppSettings
    import ragdb.desktop.app as desktop_app

    session = AuthSession(UUID("adad7c76-3f69-4c47-a9bb-1b03fef6653c"), "a@example.com", "access", "refresh", 2**31)
    observed = []

    class AcceptedDialog(QDialog):
        def __init__(self, _settings):
            super().__init__()
            self.session = session
            QTimer.singleShot(0, self.accept)

    class FakeWelcome(QMainWindow):
        def __init__(self, *_args, **_kwargs):
            super().__init__()

        def show(self):
            super().show()
            QTimer.singleShot(0, lambda: (observed.append("running"), APPLICATION.quit()))

    monkeypatch.setattr(desktop_app, "load_settings", lambda **_: AppSettings())
    monkeypatch.setattr(desktop_app, "AuthDialog", AcceptedDialog)
    monkeypatch.setattr(desktop_app, "WelcomeWindow", FakeWelcome)
    assert desktop_app.main() == 0
    assert observed == ["running"]
