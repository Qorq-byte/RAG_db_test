"""Domain-specific exceptions."""

from uuid import UUID


class RagdbError(Exception):
    """Base exception for expected application failures."""


class NotFoundError(RagdbError):
    """Requested domain object does not exist."""


class ConflictError(RagdbError):
    """Requested operation conflicts with existing state."""


class StorageError(RagdbError):
    """Persistent storage could not complete an operation."""


class CollectionNotFoundError(NotFoundError):
    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(f"知识集合不存在：{identifier}")
        self.identifier = identifier


class CollectionAlreadyExistsError(ConflictError):
    def __init__(self, name: str) -> None:
        super().__init__(f"知识集合已存在：{name}")
        self.name = name


class SourceNotFoundError(NotFoundError):
    def __init__(self, source_id: UUID) -> None:
        super().__init__(f"资料不存在：{source_id}")
        self.source_id = source_id
