from ragdb.infrastructure.retrieval.reranker import CrossEncoderReranker


class StubCrossEncoder:
    def predict(self, pairs, batch_size):
        assert batch_size == 2
        return [0.2, 0.9]


def test_reranker_is_lazy() -> None:
    reranker = CrossEncoderReranker("test", 2, lambda _: StubCrossEncoder())
    assert reranker.model_name == "test"
