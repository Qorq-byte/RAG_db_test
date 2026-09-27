"""Exercise real HTTP, credential reload, ingestion and retrieval in isolation."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from ragdb.config import AppSettings, EmbeddingSettings, StorageSettings
from ragdb.domain.models import Collection
from ragdb.infrastructure.database import SQLiteDatabase
from ragdb.runtime import ApplicationRuntime


def test_switch_cloud_embedding_endpoints_ingest_query_restart_and_rollback(tmp_path, monkeypatch):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, self.headers["Authorization"], body))
            valid = {"/first/v1/embeddings": ("Bearer key-a", "vector-a", 3),
                     "/second/compatible-mode/v1/embeddings": ("Bearer key-b", "vector-b", 4)}
            expected = valid.get(self.path)
            if expected is None:
                status, payload = 404, {"error": "not an embedding endpoint"}
            elif (self.headers["Authorization"], body["model"]) != expected[:2]:
                status, payload = 401, {"error": "invalid credential or model"}
            else:
                dimension = expected[2]
                status, payload = 200, {"data": [
                    {"index": i, "embedding": [1.0] + [0.0] * (dimension - 1)}
                    for i in reversed(range(len(body["input"])))
                ]}
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    class Credentials:
        def __init__(self): self.values = {}
        def get(self, name): return self.values.get(name)
        def set(self, name, value): self.values[name] = value
        def delete(self, name): self.values.pop(name, None)

    credentials = Credentials()
    monkeypatch.setattr("ragdb.runtime.SystemCredentialStore", lambda: credentials)
    monkeypatch.setattr("ragdb.application.model_settings.SystemCredentialStore", lambda: credentials)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        settings = AppSettings(storage=StorageSettings(data_dir=tmp_path))
        database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
        database.initialize()
        config = tmp_path / "config.toml"
        config.write_text(f"[storage]\ndata_dir = '{tmp_path.as_posix()}'\n", encoding="utf-8")
        runtime = ApplicationRuntime(settings, database, config)
        collection = runtime.collections.create(Collection(name="隔离连接检查"))
        base = f"http://127.0.0.1:{server.server_port}"
        first = EmbeddingSettings(provider="cloud", cloud_base_url=base + "/first/v1", cloud_model="vector-a", cloud_api_key="key-a")
        second = first.model_copy(update={"cloud_base_url": base + "/second/compatible-mode/v1/embeddings", "cloud_model": "vector-b"})
        from pydantic import SecretStr
        second.cloud_api_key = SecretStr("key-b")
        assert runtime.rebuild_embeddings(first).changed
        runtime.ingestion_service().ingest_text(collection, "Fixed synthetic document for embedding connectivity.")
        assert runtime.search_service().search(collection.id, "synthetic document")
        assert runtime.rebuild_embeddings(second).chunk_count > 0
        restarted = ApplicationRuntime.from_config(config)
        assert restarted.search_service().search(collection.id, "synthetic document")
        assert calls[-1][0:2] == ("/second/compatible-mode/v1/embeddings", "Bearer key-b")
        previous_profile = restarted.embedding_fingerprint
        previous_config = config.read_bytes()
        import pytest
        with pytest.raises(RuntimeError, match="HTTP 404"):
            restarted.rebuild_embeddings(second.model_copy(update={"cloud_base_url": base + "/missing"}))
        assert restarted.embedding_fingerprint == previous_profile
        assert config.read_bytes() == previous_config
        assert restarted.search_service().search(collection.id, "synthetic document")
        assert calls[-1][0:2] == ("/second/compatible-mode/v1/embeddings", "Bearer key-b")
        assert all(call[2]["encoding_format"] == "float" for call in calls)
        assert "key-a" not in config.read_text() and "key-b" not in config.read_text()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
