"""Lazy Sentence Transformers embedding adapter."""

from collections.abc import Callable, Sequence
from typing import Any


class LocalEmbeddingProvider:
    """Load a local model only when it is first used."""

    provider_name = "local"

    def __init__(
        self,
        model_name: str,
        batch_size: int = 16,
        model_loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model_loader = model_loader
        self._model: Any | None = None

    def _get_model(self) -> Any:
        if self._model is None:
            if self._model_loader is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise RuntimeError(
                        "本地嵌入需要安装 sentence-transformers 依赖"
                    ) from exc
                self._model_loader = SentenceTransformer
            self._model = self._model_loader(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        return int(self._get_model().get_sentence_embedding_dimension())

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []
        vectors = self._get_model().encode(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [list(map(float, vector)) for vector in vectors]
