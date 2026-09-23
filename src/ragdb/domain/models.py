"""Validated domain models shared by all application layers."""

from datetime import datetime, timezone
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from ragdb.domain.enums import MessageRole, RetrievalRoute, SourceStatus, SourceType, TaskStatus


NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
Sha256Hex = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]
Metadata = dict[str, JsonValue]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Collection(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    name: DisplayName
    description: str | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self


class SourcePosition(DomainModel):
    page: int | None = Field(default=None, ge=1)
    slide: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    anchor: str | None = None
    heading_path: tuple[str, ...] = ()
    code_symbol: str | None = None

    @model_validator(mode="after")
    def validate_line_range(self) -> Self:
        if self.line_end is not None and self.line_start is None:
            raise ValueError("line_start is required when line_end is set")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must not be earlier than line_start")
        return self


class Source(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    collection_id: UUID
    source_type: SourceType
    title: DisplayName
    uri: NonEmptyText
    content_hash: Sha256Hex
    status: SourceStatus = SourceStatus.PENDING
    metadata: Metadata = Field(default_factory=dict)
    imported_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)
    parser_name: str | None = None
    parser_version: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    current_generation: int = Field(default=0, ge=0)
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.updated_at < self.imported_at:
            raise ValueError("updated_at must not be earlier than imported_at")
        return self


class DocumentUnit(DomainModel):
    text: NonEmptyText
    position: SourcePosition = Field(default_factory=SourcePosition)
    metadata: Metadata = Field(default_factory=dict)


class Document(DomainModel):
    source_id: UUID
    title: DisplayName
    units: tuple[DocumentUnit, ...] = Field(min_length=1)
    metadata: Metadata = Field(default_factory=dict)


class Chunk(DomainModel):
    id: NonEmptyText
    collection_id: UUID
    source_id: UUID
    source_content_hash: Sha256Hex
    generation: int = Field(ge=1)
    ordinal: int = Field(ge=0)
    text: NonEmptyText
    normalized_text: NonEmptyText
    position: SourcePosition = Field(default_factory=SourcePosition)
    metadata: Metadata = Field(default_factory=dict)


class IngestionTask(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    collection_id: UUID
    status: TaskStatus = TaskStatus.PENDING
    started_at: AwareDatetime = Field(default_factory=utc_now)
    finished_at: AwareDatetime | None = None
    succeeded: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)

    @property
    def processed_count(self) -> int:
        return self.succeeded + self.updated + self.skipped + self.failed

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        return self


class OperationLog(DomainModel):
    id: int | None = Field(default=None, ge=1)
    collection_id: UUID | None = None
    source_id: UUID | None = None
    action: NonEmptyText
    details: Metadata = Field(default_factory=dict)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class Conversation(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    collection_id: UUID
    title: str | None = Field(default=None, max_length=256)
    provider: NonEmptyText
    model: NonEmptyText
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self


class ConversationMessage(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    sequence: int = Field(ge=0)
    role: MessageRole
    content: NonEmptyText
    created_at: AwareDatetime = Field(default_factory=utc_now)


class MessageCitation(DomainModel):
    assistant_message_id: UUID
    display_index: int = Field(ge=1)
    chunk_id: NonEmptyText
    source_id: UUID
    source_generation: int = Field(ge=1)
    source_title: DisplayName
    source_uri: NonEmptyText
    position: SourcePosition = Field(default_factory=SourcePosition)


class ChatPromptMessage(DomainModel):
    role: Literal["system", "user", "assistant"]
    content: NonEmptyText


class ChatCompletion(DomainModel):
    content: NonEmptyText


class RetrievedChunk(DomainModel):
    chunk: Chunk
    score: float
    route: RetrievalRoute


class SearchScores(DomainModel):
    semantic: float | None = None
    keyword: float | None = None
    fusion: float | None = None
    rerank: float | None = None


class SearchHit(DomainModel):
    rank: int = Field(ge=1)
    chunk_id: NonEmptyText
    source_id: UUID
    source_title: DisplayName
    source_uri: NonEmptyText
    text: NonEmptyText
    position: SourcePosition = Field(default_factory=SourcePosition)
    routes: tuple[RetrievalRoute, ...] = Field(min_length=1)
    scores: SearchScores = Field(default_factory=SearchScores)
    metadata: Metadata = Field(default_factory=dict)
