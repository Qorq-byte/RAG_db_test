from uuid import uuid4

import pytest

from ragdb.application.generation import GenerationService
from ragdb.domain.enums import ArtifactType, RetrievalRoute
from ragdb.domain.models import ChatCompletion, SearchHit


class FakeSearch:
    def __init__(self, hits):
        self.hits = hits

    def search(self, collection_id, topic, filters=None):
        return self.hits


class FakeChat:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return ChatCompletion(content=self.content)


class FakeRepository:
    def __init__(self):
        self.saved = []

    def create(self, artifact, citations):
        self.saved.append((artifact, tuple(citations)))
        return artifact


def _hit():
    return SearchHit(
        rank=1,
        chunk_id="chunk-1",
        source_id=uuid4(),
        source_title="RAG 笔记",
        source_uri="text://rag",
        source_generation=2,
        text="RAG 通过检索证据增强生成。",
        routes=(RetrievalRoute.HYBRID,),
    )


@pytest.mark.parametrize("artifact_type", [ArtifactType.SUMMARY, ArtifactType.OUTLINE, ArtifactType.NOTES])
def test_markdown_artifact_types_are_persisted_with_citations(artifact_type):
    repository = FakeRepository()
    chat = FakeChat("内容 [1]")
    service = GenerationService(FakeSearch([_hit()]), chat, repository)

    artifact = service.generate(uuid4(), artifact_type, "RAG")

    assert artifact is not None
    assert artifact.artifact_type is artifact_type
    assert artifact.content == "内容 [1]"
    assert repository.saved[0][1][0].source_generation == 2
    assert "[1] RAG 笔记" in chat.calls[0][0].content


@pytest.mark.parametrize(
    ("artifact_type", "payload", "expected"),
    [
        (ArtifactType.QUIZ, '{"questions":[{"question":"什么是 RAG？","answer":"检索增强生成"}]}', "**question**：什么是 RAG？"),
        (ArtifactType.CARDS, '{"cards":[{"front":"RAG","back":"检索增强生成"}]}', "**front**：RAG"),
    ],
)
def test_structured_artifacts_validate_and_render(artifact_type, payload, expected):
    repository = FakeRepository()
    artifact = GenerationService(FakeSearch([_hit()]), FakeChat(payload), repository).generate(uuid4(), artifact_type, "RAG")

    assert artifact is not None
    assert expected in artifact.content


def test_empty_search_skips_model_and_persistence():
    repository = FakeRepository()
    chat = FakeChat("不应调用")

    result = GenerationService(FakeSearch([]), chat, repository).generate(uuid4(), ArtifactType.SUMMARY, "未知")

    assert result is None
    assert chat.calls == []
    assert repository.saved == []


def test_invalid_structured_output_is_not_persisted():
    repository = FakeRepository()
    service = GenerationService(FakeSearch([_hit()]), FakeChat("not-json"), repository)

    with pytest.raises(RuntimeError, match="有效的学习内容 JSON"):
        service.generate(uuid4(), ArtifactType.QUIZ, "RAG")

    assert repository.saved == []
