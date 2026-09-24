import sqlite3
from pathlib import Path

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
