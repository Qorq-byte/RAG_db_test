from pathlib import Path

import httpx
import pytest

from ragdb.application.model_settings import ModelSettingsService, chat_credential_name
from ragdb.config import ChatSettings, EmbeddingSettings
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.chat.ollama import list_ollama_models


class MemoryCredentials:
    def __init__(self):
        self.values = {}

    def set(self, name, secret):
        self.values[name] = secret

    def get(self, name):
        return self.values.get(name)

    def delete(self, name):
        self.values.pop(name, None)


def test_model_settings_save_preserves_toml_and_stores_key_separately(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("# keep this comment\n[storage]\ndata_dir = 'custom'\n", encoding="utf-8")
    credentials = MemoryCredentials()
    service = ModelSettingsService(path, tmp_path / ".env", credentials)

    loaded = service.save_chat(ChatSettings(provider="cloud", cloud_model="example"), "top-secret")

    text = path.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "data_dir = 'custom'" in text
    assert "top-secret" not in text
    assert loaded.chat.cloud_api_key.get_secret_value() == "top-secret"
    assert credentials.values == {chat_credential_name(loaded.chat): "top-secret"}


def test_embedding_test_validates_vector_without_index_mutation(monkeypatch) -> None:
    class Provider:
        def embed_texts(self, texts):
            assert texts == ["RAG model connectivity test."]
            return [[0.2, 0.3]]

    monkeypatch.setattr("ragdb.application.model_settings.create_embedding_provider", lambda _: Provider())
    ModelSettingsService(credentials=MemoryCredentials()).test_embedding(EmbeddingSettings())


def test_embedding_credentials_are_scoped_to_non_secret_profile(tmp_path: Path) -> None:
    credentials = MemoryCredentials()
    service = ModelSettingsService(tmp_path / "config.toml", tmp_path / ".env", credentials)
    profile = EmbeddingSettings(provider="cloud", cloud_model="vector-a")
    service.save_embedding(profile, "vector-key-a")
    service.save_embedding(profile.model_copy(update={"cloud_model": "vector-b"}), "vector-key-b")

    assert credentials.get(f"embedding.{embedding_profile_fingerprint(profile)}.cloud_api_key") == "vector-key-a"
    assert len(credentials.values) == 2


def test_environment_secret_takes_priority_over_system_credential(tmp_path: Path, monkeypatch) -> None:
    credentials = MemoryCredentials()
    credentials.set("chat.cloud_api_key", "vault-key")
    monkeypatch.setenv("RAGDB_CHAT__CLOUD_API_KEY", "environment-key")
    service = ModelSettingsService(tmp_path / "config.toml", tmp_path / ".env", credentials)

    assert service.load().chat.cloud_api_key.get_secret_value() == "environment-key"


def test_clearing_key_removes_it_from_vault(tmp_path: Path) -> None:
    credentials = MemoryCredentials()
    credentials.set("chat.cloud_api_key", "previous-key")
    service = ModelSettingsService(tmp_path / "config.toml", tmp_path / ".env", credentials)

    service.save_chat(ChatSettings(), "")

    assert "chat.cloud_api_key" not in credentials.values
    assert "api_key" not in (tmp_path / "config.toml").read_text(encoding="utf-8")


def test_ollama_model_list_reads_installed_names(monkeypatch) -> None:
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"models": [{"name": "qwen:7b"}]}

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: Response())
    assert list_ollama_models("http://localhost:11434/") == ["qwen:7b"]


def test_ollama_model_list_normalizes_connection_errors(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(RuntimeError, match="Ollama 模型列表"):
        list_ollama_models("http://localhost:11434")


def test_chat_candidate_cannot_reuse_another_endpoint_key(tmp_path):
    service = ModelSettingsService(tmp_path / "config.toml", tmp_path / ".env", MemoryCredentials())
    first = ChatSettings(provider="cloud", cloud_base_url="https://first.example/v1")
    second = first.model_copy(update={"cloud_base_url": "https://second.example/v1"})
    service.save_chat(first, "first-key")
    with pytest.raises(ValueError, match="API Key"):
        service.prepare("chat", second)
    service.save_chat(second, "second-key")
    assert service.prepare("chat", first).cloud_api_key.get_secret_value() == "first-key"
    assert service.prepare("chat", second).cloud_api_key.get_secret_value() == "second-key"


def test_local_save_does_not_require_available_credential_backend(tmp_path):
    class UnavailableCredentials:
        def get(self, name):
            raise RuntimeError("vault unavailable")
    service = ModelSettingsService(tmp_path / "config.toml", tmp_path / ".env", UnavailableCredentials())
    assert service.save_chat(ChatSettings(local_model="offline-chat")).chat.local_model == "offline-chat"


@pytest.mark.parametrize("endpoint", ["https://user:password@example.com/v1", "https://example.com/v1?key=secret", "file:///private", "http://localhost:0"])
def test_candidate_rejects_unsafe_service_urls(endpoint):
    with pytest.raises(ValueError):
        ModelSettingsService.validate_candidate(ChatSettings(local_base_url=endpoint))


def test_ollama_embedding_candidate_requires_model_and_safe_endpoint():
    with pytest.raises(ValueError, match="模型名称"):
        ModelSettingsService.validate_candidate(EmbeddingSettings(provider="ollama", ollama_model=" "))
    with pytest.raises(ValueError, match="服务地址"):
        ModelSettingsService.validate_candidate(EmbeddingSettings(provider="ollama", ollama_base_url="http://user:pass@localhost:11434"))
