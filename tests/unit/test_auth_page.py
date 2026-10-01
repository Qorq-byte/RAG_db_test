"""The desktop gate presents OTP before collecting a registration password."""

import os
import time
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ragdb.auth import AuthError, AuthSession, PendingRegistration
from ragdb.config import AuthSettings
from ragdb.desktop.auth_page import AuthPage


APPLICATION = QApplication.instance() or QApplication([])
SETTINGS = AuthSettings(url="https://example.supabase.co", publishable_key="sb_publishable_test")
USER_ID = UUID("adad7c76-3f69-4c47-a9bb-1b03fef6653c")


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        APPLICATION.processEvents()
        QTest.qWait(5)
    APPLICATION.processEvents()
    assert predicate()


def test_registration_collects_email_then_code_then_password():
    calls = []

    class FakeAuth:
        def __init__(self, _settings):
            pass

        def request_email_code(self, email):
            calls.append(("send", email))

        def verify_email_code(self, email, code):
            calls.append(("verify", email, code))
            return PendingRegistration(USER_ID, email, "temporary", 2**31)

        def set_registration_password(self, pending, password):
            calls.append(("password", pending.email, password))

        def close(self):
            pass

    page = AuthPage(SETTINGS, auth_factory=FakeAuth, reduce_motion=True)
    page.show()
    page._switch("register")
    assert page.stack.currentIndex() == 1
    page.register_email.setText("a@example.com")
    page._send()
    wait_until(lambda: page.stack.currentIndex() == 2)
    assert calls == [("send", "a@example.com")]
    page.code.setText("12345678")
    page._verify()
    wait_until(lambda: page.stack.currentIndex() == 3)
    page.new_password.setText("abcdefgh")
    page.confirm_password.setText("abcdefgh")
    page._save_password()
    wait_until(lambda: page.stack.currentIndex() == 0)
    assert calls == [("send", "a@example.com"),
                     ("verify", "a@example.com", "12345678"),
                     ("password", "a@example.com", "abcdefgh")]
    assert page.login_email.text() == "a@example.com"
    assert page.login_password.text() == ""
    page.close()


def test_only_verified_login_emits_authentication():
    session = AuthSession(USER_ID, "a@example.com", "access", "refresh", 2**31)

    class FakeAuth:
        def __init__(self, _settings):
            pass

        def sign_in(self, email, password):
            if password == "wrong":
                raise AuthError("邮箱或密码无效")
            return session

        def close(self):
            pass

    page = AuthPage(SETTINGS, auth_factory=FakeAuth, reduce_motion=True)
    emitted = []
    page.authenticated.connect(emitted.append)
    page.login_email.setText("a@example.com")
    page.login_password.setText("wrong")
    page._login()
    wait_until(lambda: "无效" in page.status.text())
    assert emitted == []
    page.login_password.setText("abcdefgh")
    page._login()
    wait_until(lambda: len(emitted) == 1)
    assert emitted == [session]
    page.close()
