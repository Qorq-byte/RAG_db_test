"""SQLite schema initialization and version checks."""

import sqlite3

from ragdb.domain.errors import StorageError


SCHEMA_VERSION = 2

SCHEMA_SQL = """
BEGIN IMMEDIATE;

CREATE TABLE collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    parser_name TEXT,
    parser_version TEXT,
    embedding_provider TEXT,
    embedding_model TEXT,
    current_generation INTEGER NOT NULL DEFAULT 0 CHECK (current_generation >= 0),
    error_message TEXT,
    UNIQUE (collection_id, uri)
);

CREATE INDEX idx_sources_collection ON sources(collection_id);
CREATE INDEX idx_sources_hash ON sources(collection_id, content_hash);
CREATE INDEX idx_sources_status ON sources(collection_id, status);

CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_content_hash TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    position_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source_id, generation, ordinal)
);

CREATE INDEX idx_chunks_collection ON chunks(collection_id);
CREATE INDEX idx_chunks_source_generation ON chunks(source_id, generation);

CREATE TABLE ingestion_tasks (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    succeeded INTEGER NOT NULL DEFAULT 0 CHECK (succeeded >= 0),
    updated INTEGER NOT NULL DEFAULT 0 CHECK (updated >= 0),
    skipped INTEGER NOT NULL DEFAULT 0 CHECK (skipped >= 0),
    failed INTEGER NOT NULL DEFAULT 0 CHECK (failed >= 0)
);

CREATE INDEX idx_tasks_collection_started
    ON ingestion_tasks(collection_id, started_at DESC);

CREATE TABLE task_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES ingestion_tasks(id) ON DELETE CASCADE,
    source_uri TEXT NOT NULL,
    status TEXT NOT NULL,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_task_items_task ON task_items(task_id);

CREATE TABLE operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id TEXT REFERENCES collections(id) ON DELETE SET NULL,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_operation_logs_created ON operation_logs(created_at DESC);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_id UNINDEXED,
    collection_id UNINDEXED,
    source_id UNINDEXED,
    generation UNINDEXED,
    title UNINDEXED,
    text UNINDEXED,
    search_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER chunks_after_delete_fts
AFTER DELETE ON chunks
BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = OLD.id;
END;
"""


SCHEMA_V2_SQL = """
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    title TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_conversations_collection_updated
    ON conversations(collection_id, updated_at DESC);

CREATE TABLE conversation_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(conversation_id, sequence)
);

CREATE INDEX idx_conversation_messages_sequence
    ON conversation_messages(conversation_id, sequence);

CREATE TABLE message_citations (
    assistant_message_id TEXT NOT NULL REFERENCES conversation_messages(id) ON DELETE CASCADE,
    display_index INTEGER NOT NULL CHECK (display_index >= 1),
    chunk_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_generation INTEGER NOT NULL CHECK (source_generation >= 1),
    source_title TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    position_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(assistant_message_id, display_index)
);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if current_version > SCHEMA_VERSION:
        raise StorageError(
            f"数据库版本 {current_version} 高于当前支持版本 {SCHEMA_VERSION}"
        )
    try:
        if current_version == 0:
            connection.executescript(SCHEMA_SQL)
            current_version = 1
        if current_version == 1:
            connection.executescript(SCHEMA_V2_SQL)
            current_version = 2
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StorageError("初始化 SQLite 数据库失败") from exc
