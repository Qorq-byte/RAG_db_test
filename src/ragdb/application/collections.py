"""Application service for knowledge collection management."""

from collections.abc import Sequence
from ragdb.application.operation_guard import guarded_mutation

from ragdb.domain.errors import CollectionNotFoundError
from ragdb.domain.models import Collection
from ragdb.domain.ports import CollectionRepository, VectorStore


class CollectionService:
    def __init__(
        self,
        repository: CollectionRepository,
        vector_store: VectorStore,
        *, operation_gate=None,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.operation_gate = operation_gate

    @guarded_mutation
    def create(self, name: str, description: str | None = None) -> Collection:
        return self.repository.create(Collection(name=name, description=description))

    def list_all(self) -> Sequence[Collection]:
        return self.repository.list_all()

    def get_by_name(self, name: str) -> Collection:
        collection = self.repository.get_by_name(name)
        if collection is None:
            raise CollectionNotFoundError(name)
        return collection

    @guarded_mutation
    def delete_by_name(self, name: str) -> Collection:
        collection = self.get_by_name(name)
        if not self.repository.delete(collection.id):
            raise CollectionNotFoundError(name)

        # SQLite is the catalog of record. Removing it first prevents a failed
        # vector cleanup from leaving a visible collection with missing data.
        self.vector_store.delete_collection(collection.id)
        return collection
