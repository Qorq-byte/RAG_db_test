"""Local Ollama embedding adapter using its batch embed endpoint."""

import math
from collections.abc import Sequence

import httpx


class OllamaEmbeddingProvider:
    provider_name = "ollama"

    def __init__(self, model_name: str, base_url: str, timeout_seconds: float = 120.0,
                 client: httpx.Client | None = None) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError("嵌入维度将在首次成功调用后确定")
        return self._dimension

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []
        try:
            response = self._client.post(
                f"{self.base_url}/api/embed", timeout=self.timeout_seconds,
                json={"model": self.model_name, "input": list(texts)},
            )
            response.raise_for_status()
            vectors = response.json()["embeddings"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Ollama 嵌入请求失败；请检查服务、模型名称和地址。") from exc
        if not isinstance(vectors, list) or len(vectors) != len(texts) or not vectors:
            raise RuntimeError("Ollama 嵌入响应数量不匹配")
        dimension = None
        result = []
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise RuntimeError("Ollama 嵌入响应不包含有效向量")
            try:
                parsed = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Ollama 嵌入响应不包含有效向量") from exc
            if not all(math.isfinite(value) for value in parsed):
                raise RuntimeError("Ollama 嵌入响应不包含有效向量")
            dimension = dimension or len(parsed)
            if len(parsed) != dimension:
                raise RuntimeError("Ollama 嵌入响应向量维度不一致")
            result.append(parsed)
        self._dimension = dimension
        return result
