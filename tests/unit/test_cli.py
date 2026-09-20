from typer.testing import CliRunner

from ragdb.cli import ExitCode, app


runner = CliRunner()


def test_root_help_lists_command_groups() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "collection" in result.stdout
    assert "ingest" in result.stdout
    assert "doctor" in result.stdout


def test_collection_help_lists_operations() -> None:
    result = runner.invoke(app, ["collection", "--help"])

    assert result.exit_code == 0
    assert "create" in result.stdout
    assert "delete" in result.stdout
    assert "info" in result.stdout


def test_pending_command_has_consistent_exit_code() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "尚未实现" in result.output


def test_global_config_option_is_accepted() -> None:
    result = runner.invoke(app, ["--config", "other.toml", "doctor"])

    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "环境诊断" in result.output


def test_search_help_lists_metadata_filters() -> None:
    result = runner.invoke(app, ["search", "--help"])

    assert result.exit_code == 0
    assert "--tag" in result.stdout
    assert "--date-from" in result.stdout
