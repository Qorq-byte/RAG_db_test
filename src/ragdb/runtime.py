"""Shared application runtime used by CLI and desktop front ends."""

from pathlib import Path
from dataclasses import replace
from pydantic import SecretStr

from ragdb.application.chat import AnswerService
from ragdb.application.collections import CollectionService
from ragdb.application.generation import GenerationService
from ragdb.application.embedding_rebuild import EmbeddingRebuildResult, EmbeddingRebuildService
from ragdb.application.model_settings import ModelSettingsService, chat_credential_name
from ragdb.application.ingestion import LocalIngestionService
from ragdb.application.search import SearchService
from ragdb.application.sources import SourceService
from ragdb.config import AppSettings, EmbeddingSettings, load_settings
from ragdb.infrastructure.chat import create_chat_model
from ragdb.infrastructure.chunking import StructuredChunker
from ragdb.infrastructure.database import SQLiteArtifactRepository, SQLiteChunkRepository, SQLiteCollectionRepository, SQLiteConversationRepository, SQLiteDatabase, SQLiteEmbeddingOperationGate, SQLiteEmbeddingProfileRepository, SQLiteGenerationRepository, SQLiteKeywordIndex, SQLiteOperationLogRepository, SQLiteSourceRepository, SQLiteTaskRepository
from ragdb.infrastructure.embeddings import create_embedding_provider
from ragdb.infrastructure.credentials import SystemCredentialStore
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint
from ragdb.infrastructure.retrieval import CrossEncoderReranker
from ragdb.infrastructure.parsers import ParserRegistry
from ragdb.infrastructure.parsers.ocr import TesseractOcr
from ragdb.infrastructure.vectorstore import ChromaVectorStore
from ragdb.infrastructure.web import WebCrawler
from ragdb.infrastructure.github import PublicGitHubImporter


class ApplicationRuntime:
    def __init__(self, settings: AppSettings, database: SQLiteDatabase, config_path: Path = Path("config.toml")) -> None:
        self.settings = settings
        self.database = database
        self.config_path = config_path
        self.configuration_warning = None
        if settings.chat.provider == "cloud" and settings.chat.cloud_api_key is None:
            store = SystemCredentialStore()
            secret = store.get(chat_credential_name(settings.chat)) or store.get("chat.cloud_api_key")
            settings.chat = settings.chat.model_copy(update={"cloud_api_key": SecretStr(secret) if secret else None})
        self.embedding_gate = SQLiteEmbeddingOperationGate(database)
        profile = SQLiteEmbeddingProfileRepository(database).initialize(settings.embedding)
        active_settings, self.embedding_fingerprint, self.embedding_namespace = profile
        if embedding_profile_fingerprint(settings.embedding) == self.embedding_fingerprint and settings.embedding.cloud_api_key is not None:
            active_settings = active_settings.model_copy(
                update={"cloud_api_key": settings.embedding.cloud_api_key}
            )
        elif active_settings.provider == "cloud":
            secret = SystemCredentialStore().get(
                f"embedding.{self.embedding_fingerprint}.cloud_api_key"
            )
            active_settings = active_settings.model_copy(
                update={"cloud_api_key": SecretStr(secret) if secret else None}
            )
        self.settings.embedding = active_settings

    def _embedding_context(self):
        active, fingerprint, namespace = SQLiteEmbeddingProfileRepository(self.database).get()
        configured = self.settings.embedding
        secret = None
        if fingerprint == embedding_profile_fingerprint(configured):
            secret = configured.cloud_api_key
        if active.provider == "cloud" and secret is None:
            value = SystemCredentialStore().get(f"embedding.{fingerprint}.cloud_api_key")
            secret = SecretStr(value) if value else None
        active = active.model_copy(update={"cloud_api_key": secret})
        store = ChromaVectorStore(
            self.settings.storage.data_dir / self.settings.storage.chroma_directory,
            namespace_id=namespace,
            operation_scoped=True,
        )
        gate = SQLiteEmbeddingOperationGate(self.database, (fingerprint, namespace))
        return active, store, gate

    def active_embedding_settings(self):
        return SQLiteEmbeddingProfileRepository(self.database).get()[0]

    @classmethod
    def from_config(cls, config_path: Path = Path("config.toml")) -> "ApplicationRuntime":
        settings = load_settings(config_path=config_path)
        configured_fingerprint = embedding_profile_fingerprint(settings.embedding)
        database = SQLiteDatabase(settings.storage.data_dir / settings.storage.sqlite_filename)
        database.initialize()
        runtime = cls(settings, database, config_path)
        if configured_fingerprint != runtime.embedding_fingerprint:
            runtime._sync_embedding_config()
        return runtime

    def _sync_embedding_config(self) -> str | None:
        try:
            ModelSettingsService(self.config_path).persist_embedding(self.settings.embedding)
            self.configuration_warning = None
        except (OSError, RuntimeError):
            self.configuration_warning = "索引已切换，配置文件同步失败；运行时继续使用数据库中的活动模型，下次启动将重试同步。"
        return self.configuration_warning

    @property
    def collections(self) -> SQLiteCollectionRepository:
        return SQLiteCollectionRepository(self.database)

    def collection_service(self) -> CollectionService:
        _, store, gate = self._embedding_context()
        return CollectionService(self.collections, store, operation_gate=gate)

    def source_service(self) -> SourceService:
        _, store, gate = self._embedding_context()
        return SourceService(SQLiteSourceRepository(self.database), store, operation_gate=gate)

    def ingestion_service(self) -> LocalIngestionService:
        settings = self.settings
        embedding, store, gate = self._embedding_context()
        ocr = None
        if settings.ocr.enabled and settings.ocr.executable_path is not None:
            ocr = TesseractOcr(settings.ocr.executable_path, settings.ocr.languages, settings.ocr.dpi)
        return LocalIngestionService(SQLiteSourceRepository(self.database), SQLiteChunkRepository(self.database), SQLiteTaskRepository(self.database), ParserRegistry(ocr=ocr), StructuredChunker(settings.chunking), SQLiteKeywordIndex(self.database), create_embedding_provider(embedding), store, SQLiteGenerationRepository(self.database), operation_gate=gate)

    def rebuild_embeddings(self, settings: EmbeddingSettings, *, on_progress=None, should_cancel=None) -> EmbeddingRebuildResult:
        ModelSettingsService(self.config_path).store_embedding_credential(settings)
        service = EmbeddingRebuildService(
            self.database,
            self.settings.storage.data_dir / self.settings.storage.chroma_directory,
            batch_size=settings.batch_size,
            gate=self.embedding_gate,
        )
        result = service.rebuild(settings, on_progress=on_progress, should_cancel=should_cancel)
        profile = SQLiteEmbeddingProfileRepository(self.database).get()
        if profile is not None:
            self.settings.embedding, self.embedding_fingerprint, self.embedding_namespace = profile
            if self.embedding_fingerprint == embedding_profile_fingerprint(settings):
                self.settings.embedding = self.settings.embedding.model_copy(
                    update={"cloud_api_key": settings.cloud_api_key}
                )
        return replace(result, configuration_warning=self._sync_embedding_config())

    def index_maintenance_service(self):
        from ragdb.application.index_maintenance import IndexMaintenanceService

        return IndexMaintenanceService(
            self.database, self.settings.storage.data_dir / self.settings.storage.chroma_directory
        )

    def search_service(self) -> SearchService:
        settings = self.settings
        embedding, store, gate = self._embedding_context()
        reranker = None
        if settings.rerank.enabled:
            if not settings.rerank.model:
                raise ValueError("启用重排序时必须配置 rerank.model")
            reranker = CrossEncoderReranker(settings.rerank.model, settings.rerank.batch_size)
        return SearchService(
            create_embedding_provider(embedding),
            store,
            SQLiteKeywordIndex(self.database), SQLiteSourceRepository(self.database),
            vector_top_k=settings.retrieval.vector_top_k, keyword_top_k=settings.retrieval.keyword_top_k,
            result_top_k=settings.retrieval.result_top_k, rrf_k=settings.retrieval.rrf_k,
            reranker=reranker, rerank_candidate_count=settings.rerank.candidate_count,
            ensure_current=gate.ensure_current,
        )

    def answer_service(self) -> AnswerService:
        chat = self.settings.chat
        return AnswerService(self.search_service(), create_chat_model(chat), SQLiteConversationRepository(self.database), evidence_limit=chat.evidence_limit, evidence_character_budget=chat.evidence_character_budget, history_character_budget=chat.history_character_budget)

    def generation_service(self) -> GenerationService:
        chat = self.settings.chat
        return GenerationService(self.search_service(), create_chat_model(chat), SQLiteArtifactRepository(self.database), evidence_limit=chat.evidence_limit, evidence_character_budget=chat.evidence_character_budget)

    @property
    def conversations(self) -> SQLiteConversationRepository:
        return SQLiteConversationRepository(self.database)

    @property
    def artifacts(self) -> SQLiteArtifactRepository:
        return SQLiteArtifactRepository(self.database)

    @property
    def tasks(self) -> SQLiteTaskRepository:
        return SQLiteTaskRepository(self.database)

    @property
    def operation_logs(self) -> SQLiteOperationLogRepository:
        return SQLiteOperationLogRepository(self.database)

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
