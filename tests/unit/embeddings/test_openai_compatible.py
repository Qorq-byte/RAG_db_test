import json
from io import BytesIO

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
