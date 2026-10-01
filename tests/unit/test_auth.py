"""Authentication must fail closed before opening any knowledgebase."""

import json
import base64
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from ragdb.auth import AuthError, AuthService, account_settings, delete_local_account_data
from ragdb.config import AppSettings, AuthSettings, StorageSettings


USER_ID = "adad7c76-3f69-4c47-a9bb-1b03fef6653c"


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


def service(handler, credentials=None):
    return AuthService(
        AuthSettings(url="https://example.supabase.co", publishable_key="sb_publishable_test"),
        credentials=credentials or MemoryCredentials(),
        transport=httpx.MockTransport(handler),
    )


def test_registration_sends_code_before_password_and_never_stores_it():
    credentials = MemoryCredentials()

    def handler(request):
        assert request.url.path == "/auth/v1/otp"
        assert request.headers["apikey"] == "sb_publishable_test"
        assert json.loads(request.content) == {"email": "a@example.com", "create_user": True}
        return httpx.Response(200, json={})

    service(handler, credentials).request_email_code("a@example.com")
    assert credentials.values == {}


def test_email_code_confirms_server_identity_without_saving_login():
    credentials = MemoryCredentials()
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/verify"):
            assert json.loads(request.content) == {
                "email": "a@example.com", "token": "12345678", "type": "email"
            }
            return httpx.Response(200, json={"access_token": "temporary", "refresh_token": "unused"})
        if request.url.path.endswith("/user"):
            assert request.headers["authorization"] == "Bearer temporary"
            return httpx.Response(200, json={
                "id": USER_ID, "email": "a@example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"
            })
        assert request.headers["authorization"] == "Bearer temporary"
        return httpx.Response(204)

    pending = service(handler, credentials).verify_email_code(" a@example.com ", "12345678")
    assert pending.user_id == UUID(USER_ID)
    assert paths == ["/auth/v1/verify", "/auth/v1/user"]
    assert credentials.values == {}


def test_password_can_only_be_set_after_verification_and_does_not_save_session():
    credentials = MemoryCredentials()
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/verify"):
            return httpx.Response(200, json={"access_token": "temporary", "expires_in": 3600})
        if request.url.path.endswith("/user"):
            if request.method == "PUT":
                assert request.headers["authorization"] == "Bearer temporary"
                assert json.loads(request.content) == {"password": "abcdefgh"}
            return httpx.Response(200, json={"id": USER_ID, "email": "a@example.com",
                                             "email_confirmed_at": "2026-10-01T00:00:00Z"})
        return httpx.Response(200, json={})

    auth = service(handler, credentials)
    pending = auth.verify_email_code("a@example.com", "12345678")
    with pytest.raises(AuthError, match="至少 8 位"):
        auth.set_registration_password(pending, "short")
    auth.set_registration_password(pending, "abcdefgh")
    assert paths == ["/auth/v1/verify", "/auth/v1/user", "/auth/v1/user", "/auth/v1/logout"]
    assert credentials.values == {}


def test_email_code_rejects_invalid_or_expired_token():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(403, json={"msg": "invalid token"})

    auth = service(handler)
    with pytest.raises(AuthError, match="数字验证码"):
        auth.verify_email_code("a@example.com", "12345")
    assert requests == []
    with pytest.raises(AuthError, match="验证码错误或已过期"):
        auth.verify_email_code("a@example.com", "123456")
    assert requests == ["/auth/v1/verify"]


def test_resend_code_and_rate_limit():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200 if len(calls) == 1 else 429, json={})

    auth = service(handler)
    auth.request_email_code(" a@example.com ")
    assert calls == [{"email": "a@example.com", "create_user": True}]
    with pytest.raises(AuthError, match="过于频繁"):
        auth.request_email_code("a@example.com")


def test_signin_and_restore_verify_email_server_side_and_rotate_refresh_token():
    credentials = MemoryCredentials()
    refreshes = []

    def handler(request):
        if request.url.path.endswith("/user"):
            assert request.headers["authorization"].startswith("Bearer access-")
            return httpx.Response(200, json={"id": USER_ID, "email": "a@example.com", "email_confirmed_at": "2026-09-30T00:00:00Z"})
        body = json.loads(request.content)
        if request.url.params["grant_type"] == "password":
            assert body == {"email": "a@example.com", "password": "abcdefgh"}
            return httpx.Response(200, json={"access_token": "access-1", "refresh_token": "refresh-1"})
        refreshes.append(body["refresh_token"])
        return httpx.Response(200, json={"access_token": "access-2", "refresh_token": "refresh-2"})

    auth = service(handler, credentials)
    assert auth.sign_in("a@example.com", "abcdefgh").user_id == UUID(USER_ID)
    assert "abcdefgh" not in str(credentials.values)
    assert auth.restore().email == "a@example.com"
    assert refreshes == ["refresh-1"]
    assert "refresh-2" in str(credentials.values)


def test_unconfirmed_user_cannot_save_session():
    credentials = MemoryCredentials()

    def handler(request):
        if request.url.path.endswith("/user"):
            return httpx.Response(200, json={"id": USER_ID, "email": "a@example.com", "email_confirmed_at": None})
        return httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh"})

    with pytest.raises(AuthError, match="邮箱确认"):
        service(handler, credentials).sign_in("a@example.com", "abcdefgh")
    assert credentials.values == {}


def test_missing_configuration_or_session_fails_closed():
    with pytest.raises(AuthError, match="HTTPS"):
        AuthService(AuthSettings(url="http://localhost:54321", publishable_key="public"))
    with pytest.raises(AuthError, match="服务端密钥"):
        AuthService(AuthSettings(url="https://example.supabase.co", publishable_key="sb_secret_test"))
    role = base64.urlsafe_b64encode(b'{"role":"service_role"}').decode().rstrip("=")
    with pytest.raises(AuthError, match="service_role"):
        AuthService(AuthSettings(url="https://example.supabase.co", publishable_key=f"header.{role}.signature"))
    with pytest.raises(AuthError, match="先登录"):
        service(lambda _: httpx.Response(500)).restore()


def test_each_account_has_its_own_data_directory():
    base = Path("legacy-data")
    settings = AppSettings(storage=StorageSettings(data_dir=base))
    first = account_settings(settings, UUID(USER_ID))
    second = account_settings(settings, UUID("96015409-ccce-458e-95ad-e2a86251f455"))
    assert first.storage.data_dir != second.storage.data_dir
    assert settings.storage.data_dir == base
    assert first.storage.data_dir.parent == base / "accounts"


def test_account_deletion_requires_verified_session_and_server_confirmation():
    session = type("Session", (), {"user_id": UUID(USER_ID), "email": "a@example.com",
                                    "access_token": "access"})()
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.headers["authorization"] == "Bearer access"
        if request.url.path.endswith("/user"):
            return httpx.Response(200, json={"id": USER_ID, "email": "a@example.com",
                                             "email_confirmed_at": "2026-10-01T00:00:00Z"})
        assert request.url.path == "/functions/v1/delete-account"
        assert json.loads(request.content) == {"code": "12345678"}
        return httpx.Response(200, json={"deleted": True})

    service(handler).delete_account(session, "12345678")
    assert calls == ["/auth/v1/user", "/functions/v1/delete-account"]


def test_account_deletion_failure_does_not_remove_local_data(tmp_path):
    account = tmp_path / "accounts" / USER_ID
    account.mkdir(parents=True)
    (account / "notes.txt").write_text("keep", encoding="utf-8")
    session = type("Session", (), {"user_id": UUID(USER_ID), "email": "a@example.com",
                                    "access_token": "access"})()

    def handler(request):
        if request.url.path.endswith("/user"):
            return httpx.Response(200, json={"id": USER_ID, "email": "a@example.com",
                                             "email_confirmed_at": "2026-10-01T00:00:00Z"})
        return httpx.Response(404, json={})

    with pytest.raises(AuthError, match="尚未部署"):
        service(handler).delete_account(session, "12345678")
    assert (account / "notes.txt").read_text(encoding="utf-8") == "keep"


def test_local_cleanup_removes_only_target_account(tmp_path):
    first = tmp_path / "accounts" / USER_ID
    second_id = UUID("96015409-ccce-458e-95ad-e2a86251f455")
    second = tmp_path / "accounts" / str(second_id)
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "notes.txt").write_text("remove", encoding="utf-8")
    (second / "notes.txt").write_text("keep", encoding="utf-8")
    delete_local_account_data(tmp_path, UUID(USER_ID))
    assert not first.exists()
    assert (second / "notes.txt").read_text(encoding="utf-8") == "keep"
