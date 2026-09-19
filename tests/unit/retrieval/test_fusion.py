from uuid import uuid4

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.models import Chunk, RetrievedChunk
from ragdb.infrastructure.retrieval.fusion import reciprocal_rank_fusion


def make_result(identifier: str, route: RetrievalRoute) -> RetrievedChunk:
    chunk = Chunk(
        id=identifier, collection_id=uuid4(), source_id=uuid4(),
        source_content_hash="a" * 64, generation=1, ordinal=0,
        text=identifier, normalized_text=identifier,
    )
    return RetrievedChunk(chunk=chunk, score=1, route=route)


def test_rrf_is_deterministic_and_deduplicates_by_chunk_id() -> None:
    vector = [make_result("a", RetrievalRoute.VECTOR), make_result("b", RetrievalRoute.VECTOR)]
    keyword = [make_result("b", RetrievalRoute.KEYWORD), make_result("a", RetrievalRoute.KEYWORD)]

    result = reciprocal_rank_fusion([vector, keyword])

    assert [item.chunk.id for item in result] == ["a", "b"]
    assert all(item.route is RetrievalRoute.HYBRID for item in result)
