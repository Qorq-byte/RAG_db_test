"""Optional, lazy cross-encoder reranker."""

from collections.abc import Callable, Sequence
from typing import Any

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.models import RetrievedChunk


class CrossEncoderReranker:
    def __init__(self, model_name: str, batch_size: int = 4, loader: Callable[[str], Any] | None = None) -> None:
        self.model_name, self.batch_size, self._loader, self._model = model_name, batch_size, loader, None

    def _get_model(self) -> Any:
        if self._model is None:
            if self._loader is None:
                from sentence_transformers import CrossEncoder
                self._loader = CrossEncoder
            self._model = self._loader(self.model_name)
        return self._model

    def rerank(self, query: str, candidates: Sequence[RetrievedChunk], limit: int) -> Sequence[RetrievedChunk]:
        scores = self._get_model().predict([(query, item.chunk.text) for item in candidates], batch_size=self.batch_size)
        ordered = sorted(zip(candidates, scores, strict=True), key=lambda pair: (-float(pair[1]), pair[0].chunk.id))[:limit]
        return [RetrievedChunk(chunk=item.chunk, score=float(score), route=RetrievalRoute.RERANKED) for item, score in ordered]
