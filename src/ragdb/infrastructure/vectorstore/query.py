"""Recover a stale local HNSW reader in an isolated, bounded process."""

import json
import logging
from pathlib import Path
import subprocess
import sys

from chromadb.errors import InternalError


logger = logging.getLogger(__name__)


def query_collection(collection, *, directory: Path, query_embeddings, n_results, include, where=None):
    args = dict(query_embeddings=[list(vector) for vector in query_embeddings],
                n_results=n_results, include=include, where=where)
    return read_collection(collection, directory, "query", args)


def read_collection(collection, directory: Path, method: str, args: dict):
    if method not in {"query", "get"}:
        raise ValueError("Only read operations are supported")
    try:
        return getattr(collection, method)(**args)
    except InternalError as error:
        if "Nothing found on disk" not in str(error):
            raise
        command = ([sys.executable, "--index-reader"] if getattr(sys, "frozen", False)
                   else [sys.executable, "-m", "ragdb.infrastructure.vectorstore.query"])
        try:
            process = subprocess.run(command, input=json.dumps({
                "directory": str(directory.resolve()), "name": collection.name,
                "storage_id": str(collection.id), "method": method, "args": args}),
                text=True, encoding="utf-8", capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if process.returncode:
                raise error
            result = json.loads(process.stdout)
            if not isinstance(result.get("ids"), list):
                raise error
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
            raise error from exc
        logger.warning("Chroma stale HNSW reader recovered using an isolated reader process")
        return result


def reader_main():
    from ragdb.infrastructure.vectorstore.clients import open_client, close_client

    request = json.load(sys.stdin)
    if request["method"] not in {"query", "get"}:
        raise ValueError("Only read operations are supported")
    if not (Path(request["directory"]) / "chroma.sqlite3").is_file():
        raise ValueError("Database no longer exists")
    client = open_client(Path(request["directory"]))
    try:
        collection = client.get_collection(request["name"], embedding_function=None)
        if str(collection.id) != request["storage_id"]:
            raise ValueError("Collection identity changed")
        result = getattr(collection, request["method"])(**request["args"])
        print(json.dumps(result, default=lambda value: value.tolist()))
    finally:
        close_client(client)


if __name__ == "__main__":
    reader_main()
