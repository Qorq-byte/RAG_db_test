"""Serialize shared Chroma system creation/release across application threads."""

from pathlib import Path
from threading import RLock

import chromadb
from chromadb.config import Settings


_lifecycle_lock = RLock()


def open_client(directory: Path):
    # Chroma's reference counter is locked, but system creation/release is not.
    with _lifecycle_lock:
        return chromadb.PersistentClient(
            path=str(directory.resolve()), settings=Settings(anonymized_telemetry=False)
        )


def close_client(client) -> None:
    with _lifecycle_lock:
        client.close()
