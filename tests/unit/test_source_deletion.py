from uuid import uuid4

from ragdb.application.sources import SourceService
from ragdb.domain.enums import SourceType
from ragdb.domain.models import Collection, Source


def test_deleting_source_removes_current_vector_generation() -> None:
    collection = Collection(name="test")
    source = Source(collection_id=collection.id, source_type=SourceType.TEXT, title="note", uri="file:///note", content_hash="a" * 64, current_generation=2)
    class Repository:
        def get(self, identifier): return source
        def delete(self, identifier): return True
    class Vectors:
        def __init__(self): self.calls = []
        def delete_source_generation(self, *values): self.calls.append(values); return 1
    vectors = Vectors()
    assert SourceService(Repository(), vectors).delete(source.id) == source
    assert vectors.calls == [(collection.id, source.id, 2)]
