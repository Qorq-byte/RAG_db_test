"""Application services for editing and testing model configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import os
import tomlkit
from pydantic import SecretStr

from ragdb.config import AppSettings, ChatSettings, EmbeddingSettings, load_settings
from ragdb.domain.models import ChatPromptMessage
from ragdb.infrastructure.chat.factory import create_chat_model
from ragdb.infrastructure.credentials import SystemCredentialStore
from ragdb.infrastructure.embeddings.factory import create_embedding_provider


class CredentialStore(Protocol):
    def set(self, name: str, secret: str) -> None: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, name: str) -> None: ...


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
        if settings.chat.cloud_api_key is None and not self._secret_overridden("chat"):
            settings.chat = settings.chat.model_copy(update={
                "cloud_api_key": _secret_from_store(self.credentials, "chat.cloud_api_key")
            })
        if settings.embedding.cloud_api_key is None and not self._secret_overridden("embedding"):
            settings.embedding = settings.embedding.model_copy(update={
                "cloud_api_key": _secret_from_store(self.credentials, "embedding.cloud_api_key")
            })
        return settings

    def save_chat(self, settings: ChatSettings, api_key: str | None = None) -> AppSettings:
        self._save_section("chat", settings.model_dump(exclude={"cloud_api_key"}))
        self._save_secret("chat", api_key)
        return self.load()

    def save_embedding(self, settings: EmbeddingSettings, api_key: str | None = None) -> AppSettings:
        self._save_section("embedding", settings.model_dump(exclude={"cloud_api_key"}))
        self._save_secret("embedding", api_key)
        return self.load()

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
        names = {
            "chat": {"provider", "cloud_model", "cloud_base_url", "cloud_timeout_seconds", "local_model", "local_base_url", "local_timeout_seconds"},
            "embedding": {"provider", "local_model", "cloud_model", "cloud_base_url", "cloud_timeout_seconds", "batch_size"},
        }
        prefix = f"RAGDB_{section.upper()}__"
        env_names = {f"{prefix}{field.upper()}" for field in names[section]}
        overridden = {name[len(prefix):].lower() for name in env_names if name in os.environ}
        if self.env_file.exists():
            for line in self.env_file.read_text(encoding="utf-8").splitlines():
                name = line.partition("=")[0].strip().removeprefix("export ")
                if name in env_names:
                    overridden.add(name[len(prefix):].lower())
        return overridden

    def _save_secret(self, section: str, secret: str | None) -> None:
        key = f"{section}.cloud_api_key"
        if secret:
            self.credentials.set(key, secret)
        elif secret == "":
            self.credentials.delete(key)

    def _secret_overridden(self, section: str) -> bool:
        name = f"RAGDB_{section.upper()}__CLOUD_API_KEY"
        if name in os.environ:
            return True
        if not self.env_file.exists():
            return False
        return any(line.partition("=")[0].strip().removeprefix("export ") == name
                   for line in self.env_file.read_text(encoding="utf-8").splitlines())

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
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(tomlkit.dumps(document), encoding="utf-8")


def settings_with_secret(settings: ChatSettings | EmbeddingSettings, secret: str | None):
    """Return an immutable settings copy with a secret sourced from the OS vault."""
    return settings.model_copy(update={"cloud_api_key": SecretStr(secret) if secret else None})


def _is_finite_number(value: object) -> bool:
    import math

    return isinstance(value, (int, float)) and math.isfinite(value)


def _secret_from_store(credentials: CredentialStore, name: str) -> SecretStr | None:
    value = credentials.get(name)
    return SecretStr(value) if value else None
