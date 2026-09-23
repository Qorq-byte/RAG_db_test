"""Hybrid search orchestration."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import JsonValue

from ragdb.domain.enums import RetrievalRoute
from ragdb.domain.errors import IndexConfigurationChangedError
from ragdb.domain.models import SearchHit, SearchScores
from ragdb.domain.ports import EmbeddingProvider, KeywordIndex, Reranker, SourceRepository, VectorStore
from ragdb.infrastructure.retrieval.fusion import reciprocal_rank_fusion


class SearchService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        keyword_index: KeywordIndex,
        source_repository: SourceRepository,
        *,
        vector_top_k: int = 20,
        keyword_top_k: int = 20,
        result_top_k: int = 10,
        rrf_k: int = 60,
        reranker: Reranker | None = None,
        rerank_candidate_count: int = 20,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.keyword_index = keyword_index
        self.source_repository = source_repository
        self.vector_top_k = vector_top_k
        self.keyword_top_k = keyword_top_k
        self.result_top_k = result_top_k
        self.rrf_k = rrf_k
        self.reranker = reranker
        self.rerank_candidate_count = rerank_candidate_count

    def search(
        self, collection_id: UUID, query: str, filters: Mapping[str, JsonValue] | None = None
    ) -> Sequence[SearchHit]:
        query = query.strip()
        if not query:
            return []
        for source in self.source_repository.list_for_collection(collection_id):
            if source.current_generation and (source.embedding_provider, source.embedding_model) != (
                self.embedding_provider.provider_name, self.embedding_provider.model_name
            ):
                raise IndexConfigurationChangedError(collection_id)
        embeddings = self.embedding_provider.embed_texts([query])
        if len(embeddings) != 1:
            raise RuntimeError("嵌入模型必须为单条查询返回一个向量")
        vectors = self.vector_store.search(collection_id, embeddings[0], self.vector_top_k, filters)
        keywords = self.keyword_index.search(collection_id, query, self.keyword_top_k, filters)
        fused = reciprocal_rank_fusion([vectors, keywords], self.rrf_k)
        if self.reranker is not None:
            fused = self.reranker.rerank(query, fused[: self.rerank_candidate_count], self.result_top_k)
        else:
            fused = fused[: self.result_top_k]
        vector_scores = {item.chunk.id: item.score for item in vectors}
        keyword_scores = {item.chunk.id: item.score for item in keywords}
        hits: list[SearchHit] = []
        for rank, item in enumerate(fused, start=1):
            source = self.source_repository.get(item.chunk.source_id)
            if source is None:
                continue
            routes = tuple(
                route for route, score in ((RetrievalRoute.VECTOR, vector_scores.get(item.chunk.id)), (RetrievalRoute.KEYWORD, keyword_scores.get(item.chunk.id))) if score is not None
            )
            hits.append(SearchHit(
                rank=rank, chunk_id=item.chunk.id, source_id=source.id,
                source_title=source.title, source_uri=source.uri, text=item.chunk.text,
                position=item.chunk.position, routes=routes,
                scores=SearchScores(semantic=vector_scores.get(item.chunk.id), keyword=keyword_scores.get(item.chunk.id), fusion=item.score),
                metadata=item.chunk.metadata,
            ))
        return hits
