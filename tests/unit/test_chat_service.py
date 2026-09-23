from pathlib import Path
from uuid import uuid4

import pytest

from ragdb.application.chat import AnswerService, NO_EVIDENCE_ANSWER
from ragdb.domain.models import ChatCompletion, Collection, SearchHit
from ragdb.infrastructure.database import SQLiteCollectionRepository, SQLiteConversationRepository, SQLiteDatabase


class FakeSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits

    def search(self, collection_id, query):
        return self.hits


class FakeChatModel:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self) -> None:
        self.messages = []

    def complete(self, messages):
        self.messages = messages
        return ChatCompletion(content="这是有依据的回答 [1]。")


@pytest.fixture
def setup(tmp_path: Path):
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="聊天"))
    return collection, SQLiteConversationRepository(database)


def hit() -> SearchHit:
    return SearchHit(
        rank=1, chunk_id="chunk-1", source_id=uuid4(), source_title="资料", source_uri="text://rag",
        source_generation=2, text="RAG 先检索资料，再交给模型生成回答。", routes=("hybrid",),
    )


def test_answer_records_evidence_and_reuses_collection_session(setup) -> None:
    collection, repository = setup
    model = FakeChatModel()
    service = AnswerService(FakeSearch([hit()]), model, repository, evidence_limit=6, evidence_character_budget=1000, history_character_budget=500)

    result = service.ask(collection.id, "RAG 是什么？", title="RAG")
    followed = service.ask(collection.id, "再解释一次", session_id=result.conversation.id)

    assert result.content == "这是有依据的回答 [1]。"
    assert result.citations[0].source_generation == 2
    assert len(repository.list_messages(result.conversation.id)) == 4
    assert "<evidence>" in model.messages[-1].content
    assert followed.conversation.id == result.conversation.id


def test_empty_search_does_not_call_model_and_records_refusal(setup) -> None:
    collection, repository = setup
    model = FakeChatModel()
    service = AnswerService(FakeSearch([]), model, repository, evidence_limit=6, evidence_character_budget=1000, history_character_budget=500)

    result = service.ask(collection.id, "没有资料的问题")

    assert result.content == NO_EVIDENCE_ANSWER
    assert model.messages == []
    assert result.citations == ()
    assert len(repository.list_messages(result.conversation.id)) == 2


def test_session_cannot_cross_collection_boundaries(setup) -> None:
    collection, repository = setup
    service = AnswerService(FakeSearch([]), FakeChatModel(), repository, evidence_limit=6, evidence_character_budget=1000, history_character_budget=500)
    session = service.ask(collection.id, "问题").conversation

    with pytest.raises(Exception, match="指定会话不存在于该知识集合"):
        service.ask(uuid4(), "另一个集合", session_id=session.id)
