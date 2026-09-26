from pathlib import Path
from unittest.mock import Mock

import pytest
from chromadb.errors import InternalError

from ragdb.infrastructure.vectorstore.clients import open_client, close_client
from ragdb.infrastructure.vectorstore.query import query_collection


def test_fresh_process_reads_committed_vectors_without_closing_owner(tmp_path):
    client = open_client(tmp_path)
    try:
        collection = client.create_collection("reader_recovery", embedding_function=None)
        collection.add(ids=["a", "b"], embeddings=[[1., 0.], [0., 1.]],
                       documents=["first", "second"], metadatas=[{"group": 1}, {"group": 2}])
        faulty = Mock()
        faulty.name, faulty.id = collection.name, collection.id
        faulty.query.side_effect = InternalError("Nothing found on disk")
        result = query_collection(faulty, directory=tmp_path, query_embeddings=[[1., 0.]],
                                  n_results=2, include=["documents", "distances"], where={"group": 2})
        assert result["ids"] == [["b"]]
        assert result["documents"] == [["second"]]
        assert collection.count() == 2
    finally:
        close_client(client)


def test_unrelated_error_never_launches_recovery(monkeypatch):
    collection = Mock()
    collection.query.side_effect = InternalError("corrupt data")
    runner = Mock()
    monkeypatch.setattr("ragdb.infrastructure.vectorstore.query.subprocess.run", runner)
    with pytest.raises(InternalError, match="corrupt"):
        query_collection(collection, directory=Path("unused"), query_embeddings=[[1.]], n_results=1, include=[])
    runner.assert_not_called()


def test_recovery_failure_preserves_original_error(monkeypatch):
    collection = Mock()
    collection.name, collection.id = "test", "id"
    collection.query.side_effect = InternalError("Nothing found on disk")
    monkeypatch.setattr("ragdb.infrastructure.vectorstore.query.subprocess.run",
                        Mock(return_value=Mock(returncode=1)))
    with pytest.raises(InternalError, match="Nothing found"):
        query_collection(collection, directory=Path("unused"), query_embeddings=[[1.]], n_results=1, include=[])
