import hashlib
import json

import httpx
import pytest

from ragdb.config import EmbeddingSettings
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.embeddings.factory import create_embedding_provider
from ragdb.infrastructure.embeddings.ollama import OllamaEmbeddingProvider


def test_ollama_embedding_uses_batch_api_and_reports_dimension():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.path == "/api/embed"
        assert json.loads(request.content) == {"model": "embeddinggemma:latest", "input": ["one", "two"]}
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    provider = OllamaEmbeddingProvider("embeddinggemma:latest", "http://localhost:11434/", client=client)

    assert provider.embed_texts([]) == []
    assert provider.embed_texts(["one", "two"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert provider.dimension == 2
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [
    {"embeddings": []},
    {"embeddings": [[1.0], [2.0]]},
    {"embeddings": [[float("nan")]]},
    {"embeddings": [[1.0, 2.0], [3.0]]},
])
def test_ollama_embedding_rejects_invalid_vectors(payload):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    provider = OllamaEmbeddingProvider("embeddinggemma:latest", "http://localhost:11434", client=client)
    with pytest.raises(RuntimeError, match="Ollama 嵌入"):
        provider.embed_texts(["one"])


def test_ollama_embedding_factory_and_legacy_fingerprint():
    settings = EmbeddingSettings(provider="ollama", ollama_model="embeddinggemma:latest")
    assert isinstance(create_embedding_provider(settings), OllamaEmbeddingProvider)
    old = EmbeddingSettings()
    old_payload = old.model_dump(exclude={"cloud_api_key", "ollama_model", "ollama_base_url", "ollama_timeout_seconds"})
    expected = hashlib.sha256(json.dumps(old_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert embedding_profile_fingerprint(old) == expected
    assert embedding_profile_fingerprint(settings) != expected
