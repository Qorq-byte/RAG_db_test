from pathlib import Path

from typer.testing import CliRunner

from ragdb.cli import app
from ragdb.domain.enums import TaskStatus
from ragdb.domain.models import Collection, IngestionTask
from ragdb.infrastructure.database import SQLiteCollectionRepository, SQLiteDatabase, SQLiteTaskRepository


runner = CliRunner()


def _config(path: Path, data_dir: Path) -> None:
    path.write_text(f'[storage]\ndata_dir = "{data_dir.as_posix()}"\n', encoding="utf-8")


def test_init_creates_runtime_directories_and_is_idempotent(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "knowledge"
    _config(config_path, data_dir)

    first = runner.invoke(app, ["--config", str(config_path), "init"])
    second = runner.invoke(app, ["--config", str(config_path), "init"])

    assert first.exit_code == 0
    assert "已创建" in first.stdout
    assert second.exit_code == 0
    assert "已存在" in second.stdout
    assert (data_dir / "ragdb.sqlite3").is_file()
    assert (data_dir / "chroma").is_dir()
    assert (data_dir / "logs" / "ragdb.log").is_file()


def test_task_list_and_show_display_persisted_task(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "knowledge"
    _config(config_path, data_dir)
    database = SQLiteDatabase(data_dir / "ragdb.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="notes"))
    task = SQLiteTaskRepository(database).create(IngestionTask(collection_id=collection.id, status=TaskStatus.COMPLETED))

    listed = runner.invoke(app, ["--config", str(config_path), "task", "list", "--collection", "notes"])
    shown = runner.invoke(app, ["--config", str(config_path), "task", "show", str(task.id)])

    assert listed.exit_code == 0
    assert str(task.id) in listed.stdout
    assert shown.exit_code == 0
    assert "状态：completed" in shown.stdout
