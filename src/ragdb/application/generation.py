"""Evidence-bound learning artifact generation."""

import json
from collections.abc import Mapping
from uuid import UUID

from pydantic import JsonValue

from ragdb.domain.enums import ArtifactType
from ragdb.domain.models import ArtifactCitation, ChatPromptMessage, LearningArtifact


NO_EVIDENCE_ARTIFACT = "知识库中未找到足够依据，无法生成学习内容。"

_INSTRUCTIONS = {
    ArtifactType.SUMMARY: "生成简明 Markdown 摘要。",
    ArtifactType.OUTLINE: "生成层级清晰的 Markdown 提纲。",
    ArtifactType.NOTES: "生成结构化 Markdown 学习笔记。",
    ArtifactType.QUIZ: "只返回 JSON 对象，键 questions 为非空数组；每项包含 question 和 answer。",
    ArtifactType.CARDS: "只返回 JSON 对象，键 cards 为非空数组；每项包含 front 和 back。",
}


class GenerationService:
    def __init__(self, search_service, chat_model, artifact_repository, *, evidence_limit: int = 6, evidence_character_budget: int = 12000) -> None:
        self.search_service, self.chat_model, self.artifact_repository = search_service, chat_model, artifact_repository
        self.evidence_limit, self.evidence_character_budget = evidence_limit, evidence_character_budget

    def generate(self, collection_id: UUID, artifact_type: ArtifactType, topic: str, filters: Mapping[str, JsonValue] | None = None) -> LearningArtifact | None:
        hits = list(self.search_service.search(collection_id, topic, filters))[:self.evidence_limit]
        if not hits:
            return None
        evidence = "\n\n".join(f"[{i}] {hit.source_title}\n{hit.text}" for i, hit in enumerate(hits, 1))[:self.evidence_character_budget]
        prompt = f"只能依据 evidence 作答，所有事实标注 [n]。{_INSTRUCTIONS[artifact_type]}\n<evidence>\n{evidence}\n</evidence>\n主题：{topic}"
        content = self.chat_model.complete([ChatPromptMessage(role="system", content=prompt)]).content
        if artifact_type in (ArtifactType.QUIZ, ArtifactType.CARDS):
            content = self._render_json(artifact_type, content)
        artifact = LearningArtifact(collection_id=collection_id, artifact_type=artifact_type, title=topic, content=content, provider=self.chat_model.provider_name, model=self.chat_model.model_name)
        citations = [ArtifactCitation(artifact_id=artifact.id, display_index=i, chunk_id=hit.chunk_id, source_id=hit.source_id, source_generation=hit.source_generation, source_title=hit.source_title, source_uri=hit.source_uri, position=hit.position) for i, hit in enumerate(hits, 1)]
        return self.artifact_repository.create(artifact, citations)

    @staticmethod
    def _render_json(artifact_type: ArtifactType, content: str) -> str:
        try:
            items = json.loads(content)["questions" if artifact_type is ArtifactType.QUIZ else "cards"]
            left, right = ("question", "answer") if artifact_type is ArtifactType.QUIZ else ("front", "back")
            if not isinstance(items, list) or not items or any(not isinstance(x, dict) or not str(x.get(left, "")).strip() or not str(x.get(right, "")).strip() for x in items): raise ValueError
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("模型未返回有效的学习内容 JSON") from exc
        return "\n\n".join(f"## {i}\n**{left}**：{item[left]}\n\n**{right}**：{item[right]}" for i, item in enumerate(items, 1))
