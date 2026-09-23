from pathlib import Path
from uuid import uuid4

import sqlite3
import pytest

from ragdb.domain.enums import MessageRole
from ragdb.domain.models import (
    Collection,
    Conversation,
    ConversationMessage,
    MessageCitation,
    SourcePosition,
)
from ragdb.infrastructure.database.repository import (
    SQLiteCollectionRepository,
    SQLiteConversationRepository,
    SQLiteDatabase,
)
from ragdb.infrastructure.database.schema import SCHEMA_SQL, SCHEMA_VERSION


@pytest.fixture
def database(tmp_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    return database


def test_v1_database_upgrades_without_losing_existing_collections(tmp_path: Path) -> None:
    path = tmp_path / "v1.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "INSERT INTO collections (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("5cc1dd04-2aa1-4b82-98f4-48d24cb4954d", "旧集合", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )

    database = SQLiteDatabase(path)
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT name FROM collections").fetchone()[0] == "旧集合"
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'conversations'").fetchone() is not None


def test_conversation_round_trip_citations_and_collection_cascade(database: SQLiteDatabase) -> None:
    collection = Collection(name="问答")
    SQLiteCollectionRepository(database).create(collection)
    repository = SQLiteConversationRepository(database)
    conversation = repository.create(Conversation(collection_id=collection.id, provider="local", model="qwen"))
    user = ConversationMessage(conversation_id=conversation.id, sequence=0, role=MessageRole.USER, content="什么是 RAG？")
    assistant = ConversationMessage(conversation_id=conversation.id, sequence=1, role=MessageRole.ASSISTANT, content="RAG 检索资料后再生成答案。")
    citation = MessageCitation(
        assistant_message_id=assistant.id, display_index=1, chunk_id="chunk-1", source_id=uuid4(),
        source_generation=1, source_title="笔记", source_uri="text://rag", position=SourcePosition(page=2),
    )

    repository.record_turn(user, assistant, [citation])

    assert repository.get(conversation.id) is not None
    assert list(repository.list_messages(conversation.id)) == [user, assistant]
    assert list(repository.list_citations(assistant.id)) == [citation]
    SQLiteCollectionRepository(database).delete(collection.id)
    assert repository.get(conversation.id) is None
    assert repository.list_messages(conversation.id) == []


def test_record_turn_is_atomic_when_citation_is_invalid(database: SQLiteDatabase) -> None:
    collection = Collection(name="原子性")
    SQLiteCollectionRepository(database).create(collection)
    repository = SQLiteConversationRepository(database)
    conversation = repository.create(Conversation(collection_id=collection.id, provider="cloud", model="test"))
    user = ConversationMessage(conversation_id=conversation.id, sequence=0, role=MessageRole.USER, content="问题")
    assistant = ConversationMessage(conversation_id=conversation.id, sequence=1, role=MessageRole.ASSISTANT, content="回答")
    invalid = MessageCitation(
        assistant_message_id=uuid4(), display_index=1, chunk_id="chunk-1", source_id=uuid4(),
        source_generation=1, source_title="资料", source_uri="text://source",
    )

    with pytest.raises(Exception, match="引用必须属于本轮助手消息"):
        repository.record_turn(user, assistant, [invalid])

    assert repository.list_messages(conversation.id) == []
