import httpx
import pytest

from ragdb.domain.models import ChatPromptMessage
from ragdb.infrastructure.chat.ollama import OllamaChatModel
from ragdb.infrastructure.chat.openai_compatible import OpenAICompatibleChatModel


def test_openai_compatible_chat_uses_expected_request() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "答案"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    model = OpenAICompatibleChatModel("gpt-test", "https://example.test/v1/", "secret", 12, client)
    assert model.complete([ChatPromptMessage(role="user", content="问题")]).content == "答案"
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"


def test_cloud_chat_requires_api_key() -> None:
    model = OpenAICompatibleChatModel("gpt-test", "https://example.test/v1", None, 12)
    with pytest.raises(RuntimeError, match="RAGDB_CHAT__CLOUD_API_KEY"):
        model.complete([ChatPromptMessage(role="user", content="问题")])


def test_ollama_chat_uses_expected_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:11434/api/chat"
        return httpx.Response(200, json={"message": {"content": "本地答案"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    model = OllamaChatModel("qwen", "http://localhost:11434/", 12, client)
    assert model.complete([ChatPromptMessage(role="system", content="规则")]).content == "本地答案"


def test_chat_adapters_normalize_invalid_responses() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
    model = OllamaChatModel("qwen", "http://localhost:11434", 12, client)
    with pytest.raises(RuntimeError, match="响应格式错误"):
        model.complete([ChatPromptMessage(role="user", content="问题")])
