import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from ragdb.config import EmbeddingSettings
from ragdb.infrastructure.database.repository import (
    SQLiteDatabase,
    SQLiteEmbeddingProfileRepository,
    embedding_profile_fingerprint,
)
from ragdb.infrastructure.database.schema import SCHEMA_SQL, SCHEMA_VERSION


def test_profile_initialization_persists_fingerprint_without_secret(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    settings = EmbeddingSettings(provider="cloud", cloud_model="embedding-a", cloud_api_key="secret")
    repository = SQLiteEmbeddingProfileRepository(database)

    active, fingerprint, namespace = repository.initialize(settings)

    assert fingerprint == embedding_profile_fingerprint(settings)
    assert active.cloud_api_key is None
    assert namespace == "legacy"
    assert repository.initialize(EmbeddingSettings(local_model="different"))[1] == fingerprint
    with database.connect() as connection:
        assert "secret" not in connection.execute("SELECT settings_json FROM active_embedding_profile").fetchone()[0]


def test_profile_namespace_switch_is_atomic_and_fingerprint_scoped(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "db.sqlite3")
    database.initialize()
    repository = SQLiteEmbeddingProfileRepository(database)
    initial = EmbeddingSettings()
    repository.initialize(initial)
    candidate = EmbeddingSettings(provider="cloud", cloud_model="embedding-b")
    fingerprint = repository.activate(candidate, embedding_profile_fingerprint(candidate))

    assert repository.get() == (candidate, fingerprint, fingerprint)


def test_v3_schema_upgrades_with_empty_profile_table(tmp_path: Path) -> None:
    path = tmp_path / "v3.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute("PRAGMA user_version = 3")

    database = SQLiteDatabase(path)
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT COUNT(*) FROM active_embedding_profile").fetchone()[0] == 0


@pytest.mark.parametrize("provider", ["local", "cloud"])
@pytest.mark.parametrize("versioned_namespace", [False, True])
def test_pre_ollama_profile_reopens_without_changing_namespace(tmp_path, provider, versioned_namespace):
    # This is the persisted format from before Ollama fields were introduced.
    payload = json.dumps({
        "provider": provider,
        "local_model": "BAAI/bge-small-zh-v1.5",
        "cloud_model": "text-embedding-3-small",
        "cloud_base_url": "https://api.openai.com/v1",
        "cloud_timeout_seconds": 30.0,
        "batch_size": 16,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    namespace = fingerprint if versioned_namespace else "legacy"
    path = tmp_path / "old-profile.sqlite3"
    database = SQLiteDatabase(path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO active_embedding_profile "
            "(singleton_id, fingerprint, settings_json, namespace_id, updated_at) VALUES (1, ?, ?, ?, ?)",
            (fingerprint, payload, namespace, "2026-09-24T00:00:00+08:00"),
        )

    reopened = SQLiteDatabase(path)
    reopened.initialize()
    repository = SQLiteEmbeddingProfileRepository(reopened)
    active = repository.get()

    assert active[0].provider == provider
    assert active[1:] == (fingerprint, namespace)
    assert repository.initialize(EmbeddingSettings(provider="ollama")) == active
    with reopened.connect() as connection:
        assert connection.execute("SELECT settings_json FROM active_embedding_profile").fetchone()[0] == payload
