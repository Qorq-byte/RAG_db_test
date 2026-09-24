"""Application services for editing and testing model configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import os
import tempfile
import json
import hashlib
from urllib.parse import urlsplit
from dotenv import dotenv_values
import tomlkit
from pydantic import SecretStr

from ragdb.config import AppSettings, ChatSettings, EmbeddingSettings, load_settings
from ragdb.domain.models import ChatPromptMessage
from ragdb.infrastructure.chat.factory import create_chat_model
from ragdb.infrastructure.credentials import SystemCredentialStore
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.embeddings.factory import create_embedding_provider


class CredentialStore(Protocol):
    def set(self, name: str, secret: str) -> None: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, name: str) -> None: ...


def chat_credential_name(settings: ChatSettings) -> str:
    endpoint = settings.cloud_base_url.rstrip("/")
    return "chat." + hashlib.sha256(endpoint.encode("utf-8")).hexdigest() + ".cloud_api_key"


class ModelSettingsService:
    """Save non-secret TOML settings and test configured model endpoints."""

    def __init__(
        self,
        config_path: Path = Path("config.toml"),
        env_file: Path = Path(".env"),
        credentials: CredentialStore | None = None,
    ) -> None:
        self.config_path = config_path
        self.env_file = env_file
        self.credentials = credentials or SystemCredentialStore()

    def load(self) -> AppSettings:
        settings = load_settings(self.config_path, self.env_file)
        if settings.chat.provider == "cloud" and settings.chat.cloud_api_key is None and not self._secret_overridden("chat"):
            settings.chat = settings.chat.model_copy(update={
                "cloud_api_key": _secret_from_store(self.credentials, chat_credential_name(settings.chat))
                or _secret_from_store(self.credentials, "chat.cloud_api_key")
            })
        if settings.embedding.provider == "cloud" and settings.embedding.cloud_api_key is None and not self._secret_overridden("embedding"):
            fingerprint = embedding_profile_fingerprint(settings.embedding)
            settings.embedding = settings.embedding.model_copy(update={
                "cloud_api_key": _secret_from_store(
                    self.credentials, f"embedding.{fingerprint}.cloud_api_key"
                ) or _secret_from_store(self.credentials, "embedding.cloud_api_key")
            })
        return settings

    def save_chat(self, settings: ChatSettings, api_key: str | None = None) -> AppSettings:
        previous = load_settings(self.config_path, self.env_file).chat
        legacy = self.credentials.get("chat.cloud_api_key") if settings.provider == "cloud" else None
        if legacy:
            self.credentials.set(chat_credential_name(previous), legacy)
            self.credentials.delete("chat.cloud_api_key")
        name = chat_credential_name(settings)
        if api_key:
            self.credentials.set(name, api_key)
        elif api_key == "":
            self.credentials.delete(name)
            if name == chat_credential_name(previous):
                self.credentials.delete("chat.cloud_api_key")
        self._save_section("chat", settings.model_dump(exclude={"cloud_api_key"}))
        return self.load()

    def prepare(self, section: str, settings, api_key: str | None = None):
        """Resolve external overrides and credentials without saving candidate settings."""
        effective = getattr(load_settings(self.config_path, self.env_file), section)
        values = settings.model_dump(exclude={"cloud_api_key"})
        sources = self.field_sources(section)
        for field in sources:
            if field != "cloud_api_key":
                values[field] = getattr(effective, field)
        candidate = type(settings).model_validate(values)
        if candidate.provider == "cloud":
            if "cloud_api_key" in sources:
                secret = effective.cloud_api_key
            elif api_key is not None:
                secret = SecretStr(api_key) if api_key else None
            elif section == "embedding":
                secret = _secret_from_store(self.credentials, f"embedding.{embedding_profile_fingerprint(candidate)}.cloud_api_key")
            else:
                secret = _secret_from_store(self.credentials, chat_credential_name(candidate))
                if secret is None and candidate.cloud_base_url.rstrip("/") == effective.cloud_base_url.rstrip("/"):
                    secret = _secret_from_store(self.credentials, "chat.cloud_api_key")
            candidate = candidate.model_copy(update={"cloud_api_key": secret})
        self.validate_candidate(candidate)
        return candidate

    @staticmethod
    def validate_candidate(settings, *, require_key: bool = True) -> None:
        model = settings.local_model if settings.provider == "local" else settings.cloud_model
        if not model.strip():
            raise ValueError("请填写模型名称或本地模型路径。")
        endpoint = settings.cloud_base_url if settings.provider == "cloud" else getattr(settings, "local_base_url", None)
        if endpoint is not None:
            try:
                parsed = urlsplit(endpoint)
                valid = parsed.scheme in {"http", "https"} and parsed.hostname and parsed.port != 0
                valid = valid and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("服务地址须为 HTTP(S) 地址，不能包含密码、查询参数或片段。")
        if require_key and settings.provider == "cloud" and not settings.cloud_api_key:
            raise ValueError("请填写云端 API Key；更换服务地址时需重新提供密钥。")

    def clear_credential(self, section: str, settings) -> None:
        if "cloud_api_key" in self.field_sources(section):
            raise ValueError("密钥由环境变量或 .env 管理，请修改对应配置来源。")
        key = chat_credential_name(settings) if section == "chat" else f"embedding.{embedding_profile_fingerprint(settings)}.cloud_api_key"
        self.credentials.delete(key)
        if section == "chat":
            previous = load_settings(self.config_path, self.env_file).chat
            if chat_credential_name(previous) == key:
                self.credentials.delete("chat.cloud_api_key")
        else:
            self.credentials.delete("embedding.cloud_api_key")

    def save_embedding(self, settings: EmbeddingSettings, api_key: str | None = None) -> AppSettings:
        self._save_section("embedding", settings.model_dump(exclude={"cloud_api_key"}))
        fingerprint = embedding_profile_fingerprint(settings)
        key_name = f"embedding.{fingerprint}.cloud_api_key"
        if api_key:
            self.credentials.set(key_name, api_key)
        elif api_key == "":
            self.credentials.delete(key_name)
            self.credentials.delete("embedding.cloud_api_key")
        return self.load()

    def store_embedding_credential(self, settings: EmbeddingSettings) -> None:
        if settings.provider == "cloud" and settings.cloud_api_key is not None:
            fingerprint = embedding_profile_fingerprint(settings)
            self.credentials.set(
                f"embedding.{fingerprint}.cloud_api_key",
                settings.cloud_api_key.get_secret_value(),
            )

    def persist_embedding(self, settings: EmbeddingSettings) -> None:
        """Sync the published profile without loading credentials or environment overrides."""
        self._save_section("embedding", settings.model_dump(exclude={"cloud_api_key"}))

    def test_chat(self, settings: ChatSettings) -> None:
        model = create_chat_model(settings)
        model.complete([ChatPromptMessage(role="user", content="Reply with OK.")])

    def test_embedding(self, settings: EmbeddingSettings) -> None:
        provider = create_embedding_provider(settings)
        vectors = provider.embed_texts(["RAG model connectivity test."])
        if len(vectors) != 1 or not vectors[0] or not all(map(_is_finite_number, vectors[0])):
            raise RuntimeError("嵌入服务返回了无效向量。")

    def ollama_models(self, base_url: str, timeout_seconds: float = 10.0) -> list[str]:
        from ragdb.infrastructure.chat.ollama import list_ollama_models

        return list_ollama_models(base_url, timeout_seconds)

    def environment_overrides(self, section: str) -> set[str]:
        return set(self.field_sources(section))

    def field_sources(self, section: str) -> dict[str, str]:
        fields = (ChatSettings if section == "chat" else EmbeddingSettings).model_fields
        prefix = f"ragdb_{section}"
        result = {}
        for label, raw in ((".env", dotenv_values(self.env_file)), ("环境变量", os.environ)):
            values = {key.lower(): value for key, value in raw.items() if value is not None}
            if prefix in values:
                try:
                    parent = json.loads(values[prefix])
                except (ValueError, TypeError):
                    parent = {}
                if isinstance(parent, dict):
                    for field in parent.keys() & fields.keys():
                        result[field] = f"{label}：{prefix.upper()}"
            for field in fields:
                key = f"{prefix}__{field}"
                if key in values:
                    result[field] = f"{label}：{key.upper()}"
        return result

    def _secret_overridden(self, section: str) -> bool:
        return "cloud_api_key" in self.field_sources(section)

    def _save_section(self, section: str, values: dict[str, Any]) -> None:
        document = tomlkit.document()
        if self.config_path.exists():
            try:
                document = tomlkit.parse(self.config_path.read_text(encoding="utf-8"))
            except (tomlkit.exceptions.ParseError, OSError) as exc:
                raise RuntimeError("配置文件无法读取，未修改任何设置。") from exc
        table = document.get(section)
        if not isinstance(table, tomlkit.items.Table):
            table = tomlkit.table()
            document[section] = table
        for name, value in values.items():
            table[name] = str(value) if isinstance(value, Path) else value
        table.pop("cloud_api_key", None)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.config_path.parent,
                                             prefix=".ragdb-config-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(tomlkit.dumps(document))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.config_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def settings_with_secret(settings: ChatSettings | EmbeddingSettings, secret: str | None):
    """Return an immutable settings copy with a secret sourced from the OS vault."""
    return settings.model_copy(update={"cloud_api_key": SecretStr(secret) if secret else None})


def _is_finite_number(value: object) -> bool:
    import math

    return isinstance(value, (int, float)) and math.isfinite(value)


def _secret_from_store(credentials: CredentialStore, name: str) -> SecretStr | None:
    value = credentials.get(name)
    return SecretStr(value) if value else None
