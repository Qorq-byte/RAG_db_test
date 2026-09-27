"""Offline frozen-package integration check, always using synthetic data."""

def run():
    import json
    from importlib.resources import files
    from pathlib import Path
    import tempfile
    import PySide6.QtWidgets
    import docx
    import pptx
    import pymupdf
    import keyring
    import sentence_transformers
    from ragdb.config import AppSettings, StorageSettings
    from ragdb.application.backup import BackupService
    from ragdb.application.evaluation import benchmark
    from ragdb.infrastructure.database import SQLiteDatabase
    from ragdb.infrastructure.vectorstore.clients import open_client, close_client
    from ragdb.infrastructure.vectorstore.query import read_collection
    from chromadb.errors import InternalError

    dataset = json.loads(files("ragdb").joinpath("evaluation_data/benchmark.json").read_text(encoding="utf-8"))
    assert len(list(files("ragdb").joinpath("desktop/assets/welcome").iterdir())) >= 20
    with tempfile.TemporaryDirectory(prefix="ragdb-package-check-") as directory:
        root = Path(directory)
        settings = AppSettings(storage=StorageSettings(data_dir=root / "library"))
        report = benchmark(dataset, settings, root / "benchmark", offline=True)
        assert report["passed"]
        SQLiteDatabase(settings.storage.data_dir / "ragdb.sqlite3").initialize()
        client = open_client(settings.storage.data_dir / "chroma")
        try:
            collection = client.create_collection("package_check", embedding_function=None)
            collection.add(ids=["a"], embeddings=[[1., 0.]])
            class Stale:
                name = collection.name
                id = collection.id
                def get(self, **kwargs):
                    raise InternalError("Nothing found on disk")
            assert read_collection(Stale(), settings.storage.data_dir / "chroma", "get", {"include": ["embeddings"]})["ids"] == ["a"]
        finally:
            close_client(client)
        archive = root / "backup.zip"
        BackupService(settings).create(archive)
        assert BackupService.verify(archive)["valid"]
        assert BackupService.restore(archive, root / "restored").is_file()
    print(json.dumps({"status": "passed", "checks": ["imports", "offline assets", "retrieval evaluation", "isolated reader", "backup restore"]}))
    return 0
