"""Application configuration loading and validation."""

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class ConfigSection(BaseModel):
    """Base model for strict configuration sections."""

    model_config = ConfigDict(extra="forbid")


class StorageSettings(ConfigSection):
    data_dir: Path = Path(".data")
    sqlite_filename: str = "ragdb.sqlite3"
    chroma_directory: str = "chroma"


class EmbeddingSettings(ConfigSection):
    provider: Literal["local", "cloud"] = "local"
    local_model: str = "BAAI/bge-small-zh-v1.5"
    cloud_model: str = "text-embedding-3-small"
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_api_key: SecretStr | None = None
    cloud_timeout_seconds: float = Field(default=30.0, gt=0)
    batch_size: int = Field(default=16, ge=1)


class ChunkingSettings(ConfigSection):
    max_characters: int = Field(default=1200, ge=200)
    overlap_characters: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.overlap_characters >= self.max_characters:
            raise ValueError("overlap_characters must be smaller than max_characters")
        return self


class RetrievalSettings(ConfigSection):
    vector_top_k: int = Field(default=20, ge=1)
    keyword_top_k: int = Field(default=20, ge=1)
    result_top_k: int = Field(default=10, ge=1)
    rrf_k: int = Field(default=60, ge=1)


class CrawlSettings(ConfigSection):
    max_depth: int = Field(default=1, ge=0)
    max_pages: int = Field(default=50, ge=1)
    requests_per_second: float = Field(default=1.0, gt=0)
    timeout_seconds: float = Field(default=20.0, gt=0)
    user_agent: str = "ragdb/0.1"
    retry_count: int = Field(default=2, ge=0, le=5)


class RerankSettings(ConfigSection):
    enabled: bool = False
    model: str | None = None
    candidate_count: int = Field(default=20, ge=1)
    batch_size: int = Field(default=4, ge=1)


class OcrSettings(ConfigSection):
    enabled: bool = False
    executable_path: Path | None = None
    languages: str = "chi_sim+eng"
    dpi: int = Field(default=200, ge=72, le=600)


class ChatSettings(ConfigSection):
    provider: Literal["cloud", "local"] = "local"
    cloud_model: str = "gpt-4.1-mini"
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_api_key: SecretStr | None = None
    cloud_timeout_seconds: float = Field(default=60.0, gt=0)
    local_model: str = "qwen2.5:7b"
    local_base_url: str = "http://127.0.0.1:11434"
    local_timeout_seconds: float = Field(default=120.0, gt=0)
    evidence_limit: int = Field(default=6, ge=1, le=50)
    evidence_character_budget: int = Field(default=12000, ge=500)
    history_character_budget: int = Field(default=6000, ge=0)


class AppSettings(BaseSettings):
    """Validated settings for the ragdb application."""

    model_config = SettingsConfigDict(
        env_prefix="RAGDB_",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    storage: StorageSettings = Field(default_factory=StorageSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    ocr: OcrSettings = Field(default_factory=OcrSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class SafeTomlConfigSettingsSource(TomlConfigSettingsSource):
    """Load TOML settings while refusing secrets stored in the file."""

    def __call__(self) -> dict[str, Any]:
        values = super().__call__()
        embedding = values.get("embedding")
        if isinstance(embedding, dict):
            embedding.pop("cloud_api_key", None)
        chat = values.get("chat")
        if isinstance(chat, dict):
            chat.pop("cloud_api_key", None)
        return values


def load_settings(
    config_path: Path = Path("config.toml"),
    env_file: Path = Path(".env"),
    **overrides: Any,
) -> AppSettings:
    """Load settings with overrides > environment > TOML > defaults."""

    class RuntimeSettings(AppSettings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (
                init_settings,
                env_settings,
                dotenv_settings,
                SafeTomlConfigSettingsSource(settings_cls, toml_file=config_path),
                file_secret_settings,
            )

    return RuntimeSettings(_env_file=env_file, **overrides)
