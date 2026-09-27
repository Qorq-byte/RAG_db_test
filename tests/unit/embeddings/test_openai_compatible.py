import json
from io import BytesIO

import pytest

from ragdb.infrastructure.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


class Response:
    def __init__(self, body: dict) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.body).encode()


def test_openai_compatible_provider_uses_configured_endpoint(monkeypatch) -> None:
    seen = {}

    def fake_open(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.headers["Authorization"]
        seen["timeout"] = timeout
        return Response({"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]})

    monkeypatch.setattr("ragdb.infrastructure.embeddings.openai_compatible.urlopen", fake_open)
    provider = OpenAICompatibleEmbeddingProvider("model", "https://example.test/v1/", "secret", 12)

    assert provider.embed_texts(["one", "two"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert provider.dimension == 2
    assert seen == {"url": "https://example.test/v1/embeddings", "auth": "Bearer secret", "timeout": 12}


@pytest.mark.parametrize("base", ["https://example.test/v1", "https://example.test/v1/embeddings/"])
def test_base_or_full_embedding_endpoint_and_float_format(monkeypatch, base):
    def respond(request, timeout):
        assert request.full_url == "https://example.test/v1/embeddings"
        assert json.loads(request.data) == {"model": "vector", "input": ["one"], "encoding_format": "float"}
        return Response({"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
    monkeypatch.setattr("ragdb.infrastructure.embeddings.openai_compatible.urlopen", respond)
    assert OpenAICompatibleEmbeddingProvider("vector", base, "key").embed_texts(["one"]) == [[0.1, 0.2]]


def test_vectors_follow_response_indices_not_response_order(monkeypatch):
    monkeypatch.setattr("ragdb.infrastructure.embeddings.openai_compatible.urlopen", lambda *args, **kwargs:
        Response({"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}))
    assert OpenAICompatibleEmbeddingProvider("vector", "https://example.test/v1", "key").embed_texts(["one", "two"]) == [[1.0], [2.0]]


@pytest.mark.parametrize("data", [
    [None], [{"embedding": [float("nan")]}], [{"embedding": [float("inf")]}],
    [{"embedding": [True]}], [{"embedding": ["secret-response"]}],
    [{"index": 1, "embedding": [1.0]}], [{"index": False, "embedding": [1.0]}],
])
def test_rejects_invalid_vector_response_without_leaking_body(monkeypatch, data):
    monkeypatch.setattr("ragdb.infrastructure.embeddings.openai_compatible.urlopen", lambda *args, **kwargs: Response({"data": data}))
    with pytest.raises(RuntimeError) as error:
        OpenAICompatibleEmbeddingProvider("vector", "https://example.test/v1", "key").embed_texts(["one"])
    assert "secret-response" not in str(error.value)


@pytest.mark.parametrize("status,hint", [(401, "API Key"), (404, "嵌入"), (429, "额度")])
def test_http_errors_give_safe_actionable_guidance(monkeypatch, status, hint):
    from urllib.error import HTTPError
    def fail(request, timeout):
        raise HTTPError(request.full_url, status, "secret-response", {}, BytesIO(b"secret-response"))
    monkeypatch.setattr("ragdb.infrastructure.embeddings.openai_compatible.urlopen", fail)
    with pytest.raises(RuntimeError) as error:
        OpenAICompatibleEmbeddingProvider("vector", "https://example.test/v1", "key").embed_texts(["one"])
    assert hint in str(error.value)
    assert "secret-response" not in str(error.value)
