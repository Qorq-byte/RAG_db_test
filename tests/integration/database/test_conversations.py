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


def test_delete_selected_conversations_cascades_only_selected_history(database):
    from ragdb.domain.enums import SourceType
    from ragdb.domain.models import Source
    from ragdb.infrastructure.database import SQLiteSourceRepository
    collection = SQLiteCollectionRepository(database).create(Collection(name="可选删除"))
    other = SQLiteCollectionRepository(database).create(Collection(name="另一个集合"))
    sources = SQLiteSourceRepository(database)
    source = sources.create(Source(collection_id=collection.id, source_type=SourceType.TEXT,
        title="保留资料", uri="manual://retained", content_hash="a" * 64))
    repo = SQLiteConversationRepository(database)
    conversations = [repo.create(Conversation(collection_id=owner.id, provider="test", model="test"))
                     for owner in (collection, collection, collection, other)]
    assistants = []
    for conversation in conversations:
        user = ConversationMessage(conversation_id=conversation.id, sequence=0, role=MessageRole.USER, content="问题")
        assistant = ConversationMessage(conversation_id=conversation.id, sequence=1, role=MessageRole.ASSISTANT, content="回答")
        assistants.append(assistant)
        repo.record_turn(user, assistant, [MessageCitation(assistant_message_id=assistant.id,
            display_index=1, chunk_id="retained", source_id=source.id, source_generation=1,
            source_title=source.title, source_uri=source.uri)])
    ids = [conversations[0].id, conversations[2].id]
    assert repo.delete_many(collection.id, ids + [ids[0], uuid4()]) == 2
    reopened = SQLiteConversationRepository(SQLiteDatabase(database.path))
    for index in (0, 2):
        assert reopened.get(conversations[index].id) is None
        assert reopened.list_messages(conversations[index].id) == []
        assert reopened.list_citations(assistants[index].id) == []
    for index in (1, 3):
        assert reopened.get(conversations[index].id) is not None
        assert len(reopened.list_messages(conversations[index].id)) == 2
        assert len(reopened.list_citations(assistants[index].id)) == 1
    assert sources.get(source.id) == source
    assert repo.delete_many(collection.id, ids) == 0
    assert repo.delete_many(collection.id, []) == 0


def test_batch_deletion_rolls_back_on_cross_collection_selection(database):
    from ragdb.domain.errors import StorageError
    collections = SQLiteCollectionRepository(database)
    first, second = [collections.create(Collection(name=name)) for name in ("一", "二")]
    repo = SQLiteConversationRepository(database)
    ours = repo.create(Conversation(collection_id=first.id, provider="test", model="test"))
    theirs = repo.create(Conversation(collection_id=second.id, provider="test", model="test"))
    with pytest.raises(StorageError, match="不属于"):
        repo.delete_many(first.id, [ours.id, theirs.id])
    assert repo.get(ours.id) is not None
    assert repo.get(theirs.id) is not None


def test_batch_deletion_rolls_back_on_database_error(database):
    from ragdb.domain.errors import StorageError
    collection = SQLiteCollectionRepository(database).create(Collection(name="回滚"))
    repo = SQLiteConversationRepository(database)
    first, second = [repo.create(Conversation(collection_id=collection.id, title=title, provider="test", model="test"))
                     for title in ("first", "blocked")]
    with database.connect() as connection:
        connection.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON conversations "
            "WHEN OLD.title = 'blocked' BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(StorageError, match="均未删除"):
        repo.delete_many(collection.id, [first.id, second.id])
    assert repo.get(first.id) is not None
    assert repo.get(second.id) is not None


def test_manager_can_list_conversations_beyond_recent_twenty(database):
    collection = SQLiteCollectionRepository(database).create(Collection(name="完整历史"))
    repo = SQLiteConversationRepository(database)
    for index in range(25):
        repo.create(Conversation(collection_id=collection.id, title=f"会话{index}", provider="test", model="test"))
    assert len(repo.list_for_collection(collection.id)) == 20
    assert len(repo.list_for_collection(collection.id, limit=None)) == 25
