from ragdb.infrastructure.embeddings.local import LocalEmbeddingProvider


class StubModel:
    def get_sentence_embedding_dimension(self) -> int:
        return 2

    def encode(self, texts, **kwargs):
        assert kwargs["batch_size"] == 3
        assert kwargs["normalize_embeddings"] is True
        return [[len(text), 1] for text in texts]


def test_local_provider_loads_lazily_and_normalizes_output() -> None:
    loaded: list[str] = []
    provider = LocalEmbeddingProvider(
        "test-model", batch_size=3, model_loader=lambda name: loaded.append(name) or StubModel()
    )

    assert loaded == []
    assert provider.dimension == 2
    assert loaded == ["test-model"]
    assert provider.embed_texts(["a", "abc"]) == [[1.0, 1.0], [3.0, 1.0]]
