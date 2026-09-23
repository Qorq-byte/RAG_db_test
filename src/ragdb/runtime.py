"""Shared application runtime used by CLI and desktop front ends."""

from pathlib import Path

from ragdb.application.chat import AnswerService
from ragdb.application.collections import CollectionService
from ragdb.application.generation import GenerationService
from ragdb.application.ingestion import LocalIngestionService
from ragdb.application.search import SearchService
from ragdb.application.sources import SourceService
from ragdb.config import AppSettings, load_settings
from ragdb.infrastructure.chat import create_chat_model
from ragdb.infrastructure.chunking import StructuredChunker
from ragdb.infrastructure.database import SQLiteArtifactRepository, SQLiteChunkRepository, SQLiteCollectionRepository, SQLiteConversationRepository, SQLiteDatabase, SQLiteGenerationRepository, SQLiteKeywordIndex, SQLiteSourceRepository, SQLiteTaskRepository
from ragdb.infrastructure.embeddings import create_embedding_provider
from ragdb.infrastructure.retrieval import CrossEncoderReranker
from ragdb.infrastructure.parsers import ParserRegistry
from ragdb.infrastructure.vectorstore import ChromaVectorStore
from ragdb.infrastructure.web import WebCrawler
from ragdb.infrastructure.github import PublicGitHubImporter


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

    def collection_service(self) -> CollectionService:
        return CollectionService(self.collections, ChromaVectorStore(self.settings.storage.data_dir / self.settings.storage.chroma_directory))

    def source_service(self) -> SourceService:
        return SourceService(SQLiteSourceRepository(self.database), ChromaVectorStore(self.settings.storage.data_dir / self.settings.storage.chroma_directory))

    def ingestion_service(self) -> LocalIngestionService:
        settings = self.settings
        return LocalIngestionService(SQLiteSourceRepository(self.database), SQLiteChunkRepository(self.database), SQLiteTaskRepository(self.database), ParserRegistry(), StructuredChunker(settings.chunking), SQLiteKeywordIndex(self.database), create_embedding_provider(settings.embedding), ChromaVectorStore(settings.storage.data_dir / settings.storage.chroma_directory), SQLiteGenerationRepository(self.database))

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

    def ingest_web(self, collection, url: str):
        service = self.ingestion_service()
        crawler = WebCrawler(self.settings.crawl)
        try:
            pages = crawler.crawl(url)
        finally:
            crawler.close()
        return [service.ingest_web_page(collection, page.url, page.title, page.text) for page in pages]

    def ingest_repository(self, collection, url: str):
        service = self.ingestion_service()
        importer = PublicGitHubImporter(self.settings.storage.data_dir / "cache" / "repos", service.max_file_size_bytes)
        _, files = importer.clone_and_list(url)
        return [service.ingest_file(collection, item.path, {"repository_url": item.repository_url, "repository_path": item.relative_path}) for item in files]
