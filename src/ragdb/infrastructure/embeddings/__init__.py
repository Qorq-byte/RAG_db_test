"""Embedding-provider adapters and their configuration factory."""

from ragdb.infrastructure.embeddings.factory import create_embedding_provider
from ragdb.infrastructure.embeddings.local import LocalEmbeddingProvider
from ragdb.infrastructure.embeddings.ollama import OllamaEmbeddingProvider
from ragdb.infrastructure.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider

__all__ = [
    "LocalEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "create_embedding_provider",
]
