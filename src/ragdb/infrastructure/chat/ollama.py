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
