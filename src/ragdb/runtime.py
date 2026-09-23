"""Shared application runtime used by CLI and desktop front ends."""

from pathlib import Path

from ragdb.application.chat import AnswerService
from ragdb.application.generation import GenerationService
from ragdb.application.search import SearchService
from ragdb.config import AppSettings, load_settings
from ragdb.infrastructure.chat import create_chat_model
from ragdb.infrastructure.database import SQLiteArtifactRepository, SQLiteCollectionRepository, SQLiteConversationRepository, SQLiteDatabase, SQLiteKeywordIndex, SQLiteSourceRepository
from ragdb.infrastructure.embeddings import create_embedding_provider
from ragdb.infrastructure.retrieval import CrossEncoderReranker
from ragdb.infrastructure.vectorstore import ChromaVectorStore


class ApplicationRuntime:
    def __init__(self, settings: AppSettings, database: SQLiteDatabase) -> None:
        self.settings = settings
        self.database = database

    @classmethod
    def from_config(cls, config_path: Path = Path("config.toml")) -> "ApplicationRuntime":
        settings = load_settings(config_path=config_path)
        database = SQLiteDatabase(settings.storage.data_dir / settings.storage.sqlite_filename)
        database.initialize()
        return cls(settings, database)

    @property
    def collections(self) -> SQLiteCollectionRepository:
        return SQLiteCollectionRepository(self.database)

    def search_service(self) -> SearchService:
        settings = self.settings
        reranker = None
        if settings.rerank.enabled:
            if not settings.rerank.model:
                raise ValueError("启用重排序时必须配置 rerank.model")
            reranker = CrossEncoderReranker(settings.rerank.model, settings.rerank.batch_size)
        return SearchService(
            create_embedding_provider(settings.embedding),
            ChromaVectorStore(settings.storage.data_dir / settings.storage.chroma_directory),
            SQLiteKeywordIndex(self.database), SQLiteSourceRepository(self.database),
            vector_top_k=settings.retrieval.vector_top_k, keyword_top_k=settings.retrieval.keyword_top_k,
            result_top_k=settings.retrieval.result_top_k, rrf_k=settings.retrieval.rrf_k,
            reranker=reranker, rerank_candidate_count=settings.rerank.candidate_count,
        )

    def answer_service(self) -> AnswerService:
        chat = self.settings.chat
        return AnswerService(self.search_service(), create_chat_model(chat), SQLiteConversationRepository(self.database), evidence_limit=chat.evidence_limit, evidence_character_budget=chat.evidence_character_budget, history_character_budget=chat.history_character_budget)

    def generation_service(self) -> GenerationService:
        chat = self.settings.chat
        return GenerationService(self.search_service(), create_chat_model(chat), SQLiteArtifactRepository(self.database), evidence_limit=chat.evidence_limit, evidence_character_budget=chat.evidence_character_budget)
