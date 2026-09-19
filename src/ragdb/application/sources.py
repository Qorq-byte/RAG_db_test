"""Application service for inspecting and deleting imported sources."""

from collections.abc import Sequence
from uuid import UUID

from ragdb.domain.errors import SourceNotFoundError
from ragdb.domain.models import Collection, Source
from ragdb.domain.ports import SourceRepository


class SourceService:
    def __init__(self, repository: SourceRepository) -> None:
        self.repository = repository

    def list_for_collection(self, collection: Collection) -> Sequence[Source]:
        return self.repository.list_for_collection(collection.id)

    def get(self, source_id: UUID) -> Source:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source

    def delete(self, source_id: UUID) -> Source:
        source = self.get(source_id)
        if not self.repository.delete(source_id):
            raise SourceNotFoundError(source_id)
        return source
