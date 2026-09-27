"""OpenAI-compatible HTTP embedding adapter."""

import json
import math
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmbeddingConnectionError(RuntimeError):
    """Static, credential-free guidance safe to display in the desktop UI."""


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
            raise EmbeddingConnectionError("请填写嵌入服务的 API Key。")
        body = json.dumps({"model": self.model_name, "input": list(texts), "encoding_format": "float"}).encode()
        endpoint = self.base_url if self.base_url.endswith("/embeddings") else f"{self.base_url}/embeddings"
        request = Request(
            endpoint,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read())
        except HTTPError as exc:
            hints = {
                400: "请检查嵌入模型名称、输入限制和接口格式。",
                401: "API Key 无效或已过期，请重新填写。",
                403: "API Key 无权调用此嵌入模型，请检查服务权限。",
                404: "未找到嵌入接口或模型。请使用支持 /embeddings 的服务及嵌入模型，不能使用聊天模型。",
                429: "请求受限，请检查服务额度或稍后重试。",
            }
            hint = hints.get(exc.code, "嵌入服务暂时不可用，请检查服务状态后重试。")
            raise EmbeddingConnectionError(f"云端嵌入请求失败（HTTP {exc.code}）。{hint}") from None
        except (URLError, TimeoutError):
            raise EmbeddingConnectionError("无法连接嵌入服务，请检查服务地址、网络或超时设置。") from None
        except (ValueError, UnicodeError):
            raise EmbeddingConnectionError("嵌入接口未返回有效 JSON，请检查服务地址。") from None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != len(texts) or not all(isinstance(item, dict) for item in data):
            raise EmbeddingConnectionError("云端嵌入响应格式错误")
        # Some compatible services omit indices; when supplied they must cover
        # every input exactly once, regardless of the response array order.
        if any("index" in item for item in data):
            indices = [item.get("index") for item in data]
            if not all(type(index) is int for index in indices) or sorted(indices) != list(range(len(texts))):
                raise EmbeddingConnectionError("云端嵌入响应的向量序号无效")
            data = sorted(data, key=lambda item: item["index"])
        vectors = [item.get("embedding") for item in data]
        if not all(isinstance(vector, list) and vector for vector in vectors):
            raise EmbeddingConnectionError("云端嵌入响应不包含有效向量")
        try:
            if any(type(value) not in (int, float) or not math.isfinite(value) for vector in vectors for value in vector):
                raise ValueError
            result = [[float(value) for value in vector] for vector in vectors]
        except (ValueError, OverflowError):
            raise EmbeddingConnectionError("云端嵌入响应不包含有效数值向量") from None
        dimension = len(result[0])
        if any(len(vector) != dimension for vector in result) or self._dimension not in (None, dimension):
            raise EmbeddingConnectionError("云端嵌入响应中的向量维度不一致")
        self._dimension = dimension
        return result
