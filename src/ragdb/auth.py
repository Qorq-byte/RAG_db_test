"""Verified Supabase email/password sessions shared by desktop and CLI."""

from __future__ import annotations

import json
import base64
import hashlib
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

import httpx

from ragdb.config import AppSettings, AuthSettings
from ragdb.infrastructure.credentials import SystemCredentialStore


class AuthError(Exception):
    """A safe, user-facing authentication error."""


@dataclass(frozen=True)
class AuthSession:
    user_id: UUID
    email: str
    access_token: str
    refresh_token: str
    expires_at: int


def account_settings(settings: AppSettings, user_id: UUID) -> AppSettings:
    """Keep pre-registration data untouched and isolate each account on disk."""

    storage = settings.storage.model_copy(
        update={"data_dir": settings.storage.data_dir / "accounts" / str(user_id)}
    )
    return settings.model_copy(update={"storage": storage})


class AuthService:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        credentials: SystemCredentialStore | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = settings.url.strip().rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/"):
            raise AuthError("请先配置有效的 HTTPS 认证项目 URL。")
        key = settings.publishable_key.strip()
        if not key or key.startswith("sb_secret_"):
            raise AuthError("请配置 Supabase 公开客户端 Key，不能使用服务端密钥。")
        if key.count(".") == 2:
            try:
                payload = key.split(".")[1]
                role = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("role")
            except (ValueError, UnicodeDecodeError, AttributeError):
                role = None
            if role == "service_role":
                raise AuthError("不能在桌面客户端配置 service_role 服务端密钥。")
        self.url = url
        self.key = key
        self.credentials = credentials or SystemCredentialStore()
        self.credential_name = f"auth.refresh.{hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]}"
        self.client = httpx.Client(
            base_url=f"{url}/auth/v1/",
            headers={"apikey": key, "Content-Type": "application/json"},
            timeout=15.0,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, *, token: str | None = None,
                 invalid_message: str | None = None, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            response = self.client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise AuthError("认证服务暂时无法连接，请检查网络后重试。") from exc
        if response.is_error:
            if response.status_code == 429:
                raise AuthError("请求过于频繁，请稍后重试。")
            if response.status_code in (400, 401, 403, 422):
                raise AuthError(invalid_message or "邮箱、密码或认证状态无效，请确认邮箱验证后重试。")
            raise AuthError("认证服务暂时不可用，请稍后重试。")
        try:
            result = response.json()
        except ValueError as exc:
            raise AuthError("认证服务返回了无效响应。") from exc
        if not isinstance(result, dict):
            raise AuthError("认证服务返回了无效响应。")
        return result

    @staticmethod
    def _verified_user(data: dict) -> tuple[UUID, str]:
        user = data.get("user", data)
        if not isinstance(user, dict) or not user.get("email_confirmed_at"):
            raise AuthError("请先输入邮件中的验证码，完成邮箱确认后再登录。")
        try:
            user_id, email = UUID(user["id"]), user["email"]
            if not isinstance(email, str) or not email:
                raise ValueError
            return user_id, email
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthError("认证服务返回了无效账号信息。") from exc

    def _session(self, data: dict) -> AuthSession:
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
            raise AuthError("认证服务没有返回有效会话。")
        # Verify the returned access token with the server rather than trusting a cached identity.
        user_id, email = self._verified_user(self._request("GET", "user", token=access))
        try:
            expires_in = int(data.get("expires_in", 3600))
            if expires_in <= 0:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise AuthError("认证服务返回了无效会话。") from exc
        session = AuthSession(user_id, email, access, refresh, int(time.time()) + expires_in)
        try:
            self.credentials.set(self.credential_name, json.dumps({"refresh_token": refresh}))
        except RuntimeError as exc:
            raise AuthError("系统凭据库不可用，无法安全保存登录状态。") from exc
        return session

    def sign_up(self, email: str, password: str) -> None:
        if not email.strip() or len(password) < 8:
            raise AuthError("请输入邮箱及至少 8 位的密码。")
        data = self._request("POST", "signup", json={"email": email.strip(), "password": password})
        # A session on signup means Confirm email is disabled on the Supabase project.
        if data.get("access_token"):
            try:
                self._request("POST", "logout", token=data["access_token"])
            except AuthError:
                pass
            raise AuthError("认证项目尚未启用邮箱确认。请管理员启用 Confirm email 后再注册。")

    def verify_email_code(self, email: str, code: str) -> None:
        """Confirm a signup code without creating a saved login session."""
        address = email.strip()
        token = code.strip()
        if not address or not re.fullmatch(r"[0-9]{6,32}", token):
            raise AuthError("请输入邮箱和邮件中的数字验证码。")
        data = self._request(
            "POST", "verify", json={"email": address, "token": token, "type": "email"},
            invalid_message="验证码错误或已过期，请重新输入或重发验证码。",
        )
        access = data.get("access_token")
        if not isinstance(access, str) or not access:
            raise AuthError("认证服务没有返回有效的邮箱验证结果。")
        try:
            _, confirmed_email = self._verified_user(self._request("GET", "user", token=access))
            if confirmed_email.casefold() != address.casefold():
                raise AuthError("认证服务返回的邮箱与当前注册邮箱不一致。")
        finally:
            try:
                self._request("POST", "logout", token=access)
            except AuthError:
                pass

    def resend_confirmation(self, email: str) -> None:
        address = email.strip()
        if not address:
            raise AuthError("请输入需要验证的邮箱。")
        self._request("POST", "resend", json={"email": address, "type": "signup"})

    def sign_in(self, email: str, password: str) -> AuthSession:
        if not email.strip() or not password:
            raise AuthError("请输入邮箱和密码。")
        data = self._request(
            "POST", "token", params={"grant_type": "password"},
            json={"email": email.strip(), "password": password},
        )
        return self._session(data)

    def restore(self) -> AuthSession:
        try:
            saved = self.credentials.get(self.credential_name)
        except RuntimeError as exc:
            raise AuthError("系统凭据库不可用，无法读取登录状态。") from exc
        if not saved:
            raise AuthError("请先登录已验证邮箱账号。")
        try:
            refresh = json.loads(saved)["refresh_token"]
            if not isinstance(refresh, str) or not refresh:
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthError("本机登录状态无效，请重新登录。") from exc
        data = self._request(
            "POST", "token", params={"grant_type": "refresh_token"},
            json={"refresh_token": refresh},
        )
        return self._session(data)

    def sign_out(self, session: AuthSession | None = None) -> None:
        if session is not None:
            try:
                self._request("POST", "logout", token=session.access_token)
            except AuthError:
                pass
        try:
            self.credentials.delete(self.credential_name)
        except RuntimeError as exc:
            raise AuthError("系统凭据库不可用，无法清除登录状态。") from exc
