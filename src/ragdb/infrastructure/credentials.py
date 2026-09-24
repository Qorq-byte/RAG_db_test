"""Secure storage for provider credentials."""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError


class SystemCredentialStore:
    """Store API keys in the operating system's credential vault."""

    SERVICE_NAME = "ragdb"

    def set(self, name: str, secret: str) -> None:
        try:
            keyring.set_password(self.SERVICE_NAME, name, secret)
        except KeyringError as exc:
            raise RuntimeError("系统凭据库不可用，未保存 API Key。") from exc

    def get(self, name: str) -> str | None:
        try:
            return keyring.get_password(self.SERVICE_NAME, name)
        except KeyringError as exc:
            raise RuntimeError("系统凭据库不可用，无法读取 API Key。") from exc

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self.SERVICE_NAME, name)
        except keyring.errors.PasswordDeleteError:
            return
        except KeyringError as exc:
            raise RuntimeError("系统凭据库不可用，未能清除 API Key。") from exc
