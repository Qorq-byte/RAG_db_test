"""Application service for inspecting and deleting imported sources."""

from collections.abc import Sequence
from uuid import UUID
from ragdb.application.operation_guard import guarded_mutation

from ragdb.domain.errors import SourceNotFoundError
from ragdb.domain.models import Collection, Source
from ragdb.domain.ports import SourceRepository
from ragdb.domain.ports import VectorStore


class SourceService:
    def __init__(self, repository: SourceRepository, vector_store: VectorStore | None = None, *, operation_gate=None) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.operation_gate = operation_gate

    def list_for_collection(self, collection: Collection) -> Sequence[Source]:
        return self.repository.list_for_collection(collection.id)

    def get(self, source_id: UUID) -> Source:
        source = self.repository.get(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source

    @guarded_mutation
    def delete(self, source_id: UUID) -> Source:
        source = self.get(source_id)
        if self.vector_store is not None and source.current_generation:
            self.vector_store.delete_source_generation(source.collection_id, source.id, source.current_generation)
        if not self.repository.delete(source_id):
            raise SourceNotFoundError(source_id)
        return source
