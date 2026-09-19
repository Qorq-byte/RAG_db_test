"""Deterministic reciprocal-rank fusion."""

from collections.abc import Sequence

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.models import RetrievedChunk


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[RetrievedChunk]], k: int = 60
) -> Sequence[RetrievedChunk]:
    """Merge ranked lists by chunk ID, preserving a stable tie break."""
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}
    routes: dict[str, set[RetrievalRoute]] = {}
    first_seen: dict[str, tuple[int, int]] = {}
    for list_index, results in enumerate(result_lists):
        for rank, result in enumerate(results, start=1):
            chunk_id = result.chunk.id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            chunks[chunk_id] = result
            routes.setdefault(chunk_id, set()).add(result.route)
            first_seen.setdefault(chunk_id, (list_index, rank))
    fused = sorted(scores, key=lambda item: (-scores[item], first_seen[item], item))
    return [
        RetrievedChunk(
            chunk=chunks[chunk_id].chunk,
            score=scores[chunk_id],
            route=(RetrievalRoute.HYBRID if len(routes[chunk_id]) > 1 else next(iter(routes[chunk_id]))),
        )
        for chunk_id in fused
    ]
