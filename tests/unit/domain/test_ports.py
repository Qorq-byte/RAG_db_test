from collections.abc import Sequence

from ragdb.domain.ports import EmbeddingProvider


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-model"
    dimension = 2

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[float(len(text)), 1.0] for text in texts]


def test_embedding_provider_protocol_is_runtime_checkable() -> None:
    provider = FakeEmbeddingProvider()

    assert isinstance(provider, EmbeddingProvider)
    assert provider.embed_texts(["abc"]) == [[3.0, 1.0]]
