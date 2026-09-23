"""OpenAI-compatible chat-completions adapter."""

from collections.abc import Sequence

import httpx

from ragdb.domain.models import ChatCompletion, ChatPromptMessage


class OpenAICompatibleChatModel:
    provider_name = "cloud"

    def __init__(self, model_name: str, base_url: str, api_key: str | None, timeout_seconds: float, client: httpx.Client | None = None) -> None:
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()

    def complete(self, messages: Sequence[ChatPromptMessage]) -> ChatCompletion:
        if not self.api_key:
            raise RuntimeError("云端问答需要配置 RAGDB_CHAT__CLOUD_API_KEY")
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions", timeout=self.timeout_seconds,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model_name, "messages": [message.model_dump() for message in messages]},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"云端问答请求失败：{exc}") from exc
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("云端问答响应格式错误") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("云端问答响应不包含有效文本")
        return ChatCompletion(content=content)
