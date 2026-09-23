"""Shared domain enumerations."""

from enum import StrEnum


class SourceType(StrEnum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    WORD = "word"
    POWERPOINT = "powerpoint"
    CODE = "code"
    WEB = "web"
    GITHUB_REPOSITORY = "github_repository"
    MANUAL_TEXT = "manual_text"


class SourceStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    OCR_REQUIRED = "ocr_required"
    FAILED = "failed"
    DELETED = "deleted"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskItemStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    FAILED = "failed"


class RetrievalRoute(StrEnum):
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    RERANKED = "reranked"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
