"""Ollama local chat adapter."""

from collections.abc import Sequence

import httpx

from ragdb.domain.models import ChatCompletion, ChatPromptMessage


class OllamaChatModel:
    provider_name = "local"

    def __init__(self, model_name: str, base_url: str, timeout_seconds: float, client: httpx.Client | None = None) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()

    def complete(self, messages: Sequence[ChatPromptMessage]) -> ChatCompletion:
        try:
            response = self._client.post(
                f"{self.base_url}/api/chat", timeout=self.timeout_seconds,
                json={"model": self.model_name, "stream": False, "messages": [message.model_dump() for message in messages]},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"本地问答请求失败：{exc}") from exc
        try:
            content = response.json()["message"]["content"]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("本地问答响应格式错误") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("本地问答响应不包含有效文本")
        return ChatCompletion(content=content)


def list_ollama_models(base_url: str, timeout_seconds: float = 10.0) -> list[str]:
    """Return installed Ollama model names from its local tags endpoint."""
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        models = payload["models"]
        names = [model["name"] for model in models]
        if not all(isinstance(name, str) and name for name in names):
            raise ValueError("invalid model name")
        return names
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("无法读取 Ollama 模型列表，请确认服务已启动。") from exc
