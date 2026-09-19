"""OpenAI-compatible HTTP embedding adapter."""

import json
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenAICompatibleEmbeddingProvider:
    provider_name = "cloud"

    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError("嵌入维度将在首次成功调用后确定")
        return self._dimension

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError("云端嵌入需要配置 RAGDB_EMBEDDING__CLOUD_API_KEY")
        body = json.dumps({"model": self.model_name, "input": list(texts)}).encode()
        request = Request(
            f"{self.base_url}/embeddings",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"云端嵌入请求失败：{exc}") from exc
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise RuntimeError("云端嵌入响应格式错误")
        vectors = [item.get("embedding") for item in data]
        if not all(isinstance(vector, list) and vector for vector in vectors):
            raise RuntimeError("云端嵌入响应不包含有效向量")
        self._dimension = len(vectors[0])
        if any(len(vector) != self._dimension for vector in vectors):
            raise RuntimeError("云端嵌入响应中的向量维度不一致")
        return [[float(value) for value in vector] for vector in vectors]
