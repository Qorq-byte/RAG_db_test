from types import SimpleNamespace
from uuid import uuid4

from typer.testing import CliRunner

import ragdb.cli as cli
from ragdb.application.index_maintenance import IndexInventory, IndexInventoryItem
from ragdb.domain.errors import ConflictError


runner = CliRunner()


def test_cli_preview_reports_candidates_and_unknown_objects(monkeypatch):
    result = IndexInventory("preview-token", "a" * 64, "a" * 64, (
        IndexInventoryItem("old-name", uuid4(), "资料", "legacy", 8, "stale", "可清理"),
        IndexInventoryItem("foreign", None, None, None, 2, "unknown", "需人工核查"),
    ))
    monkeypatch.setattr(cli, "_index_maintenance_service", lambda _: SimpleNamespace(preview=lambda: result))
    output = runner.invoke(cli.app, ["index", "list-stale"])
    assert output.exit_code == 0
    assert "preview-token" in output.stdout
    assert "old-name" in output.stdout and "foreign" in output.stdout
    assert "向量：8" in output.stdout and "需人工核查" in output.stdout


def test_cli_preview_empty_and_safe_failure(monkeypatch):
    monkeypatch.setattr(cli, "_index_maintenance_service", lambda _: SimpleNamespace(
        preview=lambda: IndexInventory("empty", "a" * 64, "legacy", ())
    ))
    assert "没有可清理" in runner.invoke(cli.app, ["index", "list-stale"]).stdout

    def fail():
        raise RuntimeError("sensitive-internal-response")
    monkeypatch.setattr(cli, "_index_maintenance_service", lambda _: SimpleNamespace(preview=fail))
    output = runner.invoke(cli.app, ["index", "list-stale"])
    assert output.exit_code == cli.ExitCode.STORAGE_ERROR
    assert "sensitive-internal-response" not in output.output


def test_cli_preview_conflict_has_conflict_exit_code(monkeypatch):
    def fail():
        raise ConflictError("盘点期间索引发生变化")
    monkeypatch.setattr(cli, "_index_maintenance_service", lambda _: SimpleNamespace(preview=fail))
    assert runner.invoke(cli.app, ["index", "list-stale"]).exit_code == cli.ExitCode.CONFLICT


def test_cli_preview_does_not_initialize_missing_database(tmp_path):
    config = tmp_path / "config.toml"
    missing = tmp_path / "not-created"
    config.write_text(f"[storage]\ndata_dir = '{missing.as_posix()}'\n", encoding="utf-8")
    output = runner.invoke(cli.app, ["--config", str(config), "index", "list-stale"])
    assert output.exit_code == cli.ExitCode.STORAGE_ERROR
    assert not missing.exists()
