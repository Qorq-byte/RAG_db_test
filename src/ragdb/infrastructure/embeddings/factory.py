"""Construct the configured embedding provider."""

from ragdb.config import EmbeddingSettings
from ragdb.domain.ports import EmbeddingProvider
from ragdb.infrastructure.embeddings.local import LocalEmbeddingProvider
from ragdb.infrastructure.embeddings.ollama import OllamaEmbeddingProvider
from ragdb.infrastructure.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


def create_embedding_provider(settings: EmbeddingSettings) -> EmbeddingProvider:
    if settings.provider == "local":
        return LocalEmbeddingProvider(settings.local_model, settings.batch_size)
    if settings.provider == "ollama":
        return OllamaEmbeddingProvider(
            settings.ollama_model, settings.ollama_base_url, settings.ollama_timeout_seconds,
        )
    return OpenAICompatibleEmbeddingProvider(
        settings.cloud_model,
        settings.cloud_base_url,
        settings.cloud_api_key.get_secret_value() if settings.cloud_api_key else None,
        settings.cloud_timeout_seconds,
    )
