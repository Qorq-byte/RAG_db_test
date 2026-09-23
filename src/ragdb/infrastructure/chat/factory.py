"""Construct the configured chat model."""

from ragdb.config import ChatSettings
from ragdb.domain.ports import ChatModel
from ragdb.infrastructure.chat.ollama import OllamaChatModel
from ragdb.infrastructure.chat.openai_compatible import OpenAICompatibleChatModel


def create_chat_model(settings: ChatSettings) -> ChatModel:
    if settings.provider == "local":
        return OllamaChatModel(settings.local_model, settings.local_base_url, settings.local_timeout_seconds)
    return OpenAICompatibleChatModel(
        settings.cloud_model, settings.cloud_base_url,
        settings.cloud_api_key.get_secret_value() if settings.cloud_api_key else None,
        settings.cloud_timeout_seconds,
    )
