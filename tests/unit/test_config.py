from pathlib import Path

import pytest
from pydantic import ValidationError

from ragdb.config import load_settings


def test_default_settings() -> None:
    settings = load_settings(
        config_path=Path("missing-config.toml"),
        env_file=Path("missing.env"),
    )

    assert settings.storage.data_dir == Path(".data")
    assert settings.embedding.provider == "local"
    assert settings.retrieval.result_top_k == 10
    assert settings.rerank.enabled is False


def test_toml_settings_are_loaded(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[storage]
data_dir = "custom-data"

[embedding]
provider = "cloud"
batch_size = 8
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path, env_file=tmp_path / ".env")

    assert settings.storage.data_dir == Path("custom-data")
    assert settings.embedding.provider == "cloud"
    assert settings.embedding.batch_size == 8


def test_environment_overrides_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[embedding]\nprovider = "cloud"\nbatch_size = 8\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("RAGDB_EMBEDDING__BATCH_SIZE", "4")

    settings = load_settings(config_path=config_path, env_file=tmp_path / ".env")

    assert settings.embedding.batch_size == 4
    assert settings.embedding.provider == "cloud"


def test_explicit_overrides_have_highest_priority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RAGDB_EMBEDDING__BATCH_SIZE", "4")

    settings = load_settings(
        config_path=tmp_path / "missing.toml",
        env_file=tmp_path / ".env",
        embedding={"batch_size": 2},
    )

    assert settings.embedding.batch_size == 2


def test_secret_value_is_masked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAGDB_EMBEDDING__CLOUD_API_KEY", "top-secret")

    settings = load_settings(
        config_path=tmp_path / "missing.toml",
        env_file=tmp_path / ".env",
    )

    assert settings.embedding.cloud_api_key is not None
    assert str(settings.embedding.cloud_api_key) == "**********"
    assert settings.embedding.cloud_api_key.get_secret_value() == "top-secret"


def test_secret_value_is_ignored_in_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[embedding]\ncloud_api_key = "must-not-load"\n',
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path, env_file=tmp_path / ".env")

    assert settings.embedding.cloud_api_key is None


def test_chat_secret_value_is_ignored_in_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[chat]\nprovider = "cloud"\ncloud_api_key = "must-not-load"\n',
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path, env_file=tmp_path / ".env")

    assert settings.chat.provider == "cloud"
    assert settings.chat.cloud_api_key is None


def test_invalid_values_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_settings(
            config_path=tmp_path / "missing.toml",
            env_file=tmp_path / ".env",
            chunking={"max_characters": 100},
        )


def test_chunk_overlap_must_be_smaller_than_chunk_size(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_settings(
            config_path=tmp_path / "missing.toml",
            env_file=tmp_path / ".env",
            chunking={"max_characters": 400, "overlap_characters": 400},
        )
