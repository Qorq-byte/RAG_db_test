"""SQLite persistence adapters."""

from ragdb.infrastructure.database.fts import SQLiteKeywordIndex
from ragdb.infrastructure.database.repository import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteArtifactRepository,
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteEmbeddingProfileRepository,
    SQLiteGenerationRepository,
    SQLiteOperationLogRepository,
    SQLiteSourceRepository,
    SQLiteTaskRepository,
)

__all__ = [
    "SQLiteChunkRepository",
    "SQLiteCollectionRepository",
    "SQLiteArtifactRepository",
    "SQLiteConversationRepository",
    "SQLiteDatabase",
    "SQLiteEmbeddingProfileRepository",
    "SQLiteGenerationRepository",
    "SQLiteOperationLogRepository",
    "SQLiteKeywordIndex",
    "SQLiteSourceRepository",
    "SQLiteTaskRepository",
]
