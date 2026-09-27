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


@pytest.mark.parametrize('outcome', ['success', 'failure', 'cancel'])
def test_stream_progress_and_only_complete_turns_persist(setup, outcome):
    from threading import Event
    from ragdb.infrastructure.chat.streaming import ChatCancelled
    collection, repository = setup
    cancelled = Event()
    events = []
    class StreamingModel(FakeChatModel):
        def stream(self, messages, **kwargs):
            assert not repository.list_for_collection(collection.id)
            yield 'first'
            assert ('delta', 'first') in events
            if outcome == 'failure':
                raise RuntimeError('disconnected')
            if outcome == 'cancel':
                cancelled.set()
            yield 'second'
    service = AnswerService(FakeSearch([hit()]), StreamingModel(), repository,
                            evidence_limit=6, evidence_character_budget=1000, history_character_budget=500)
    def ask():
        return service.ask(collection.id, 'question', stream=True,
                           on_event=lambda *event: events.append(event), should_cancel=cancelled.is_set)
    if outcome == 'success':
        result = ask()
        assert result.content == 'firstsecond'
        assert len(repository.list_messages(result.conversation.id)) == 2
        assert events[0] == ('stage', '正在检索知识库')
    else:
        with pytest.raises(ChatCancelled if outcome == 'cancel' else RuntimeError):
            ask()
        assert not repository.list_for_collection(collection.id)
