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


def test_doctor_help_is_available() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code in (ExitCode.SUCCESS, ExitCode.DOCTOR_FAILED)
    assert "Python 版本" in result.output


def test_global_config_option_is_accepted() -> None:
    result = runner.invoke(app, ["--config", "other.toml", "doctor"])

    assert result.exit_code in (ExitCode.SUCCESS, ExitCode.DOCTOR_FAILED)
    assert "配置解析" in result.output


def test_search_help_lists_metadata_filters() -> None:
    result = runner.invoke(app, ["search", "--help"])

    assert result.exit_code == 0
    assert "--tag" in result.stdout
    assert "--date-from" in result.stdout


def test_crawl_help_is_available() -> None:
    result = runner.invoke(app, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "起始网页" in result.stdout


def test_repo_help_is_available() -> None:
    assert runner.invoke(app, ["repo", "--help"]).exit_code == 0


def test_watch_management_explains_foreground_mode() -> None:
    assert "前台监听" in runner.invoke(app, ["watch", "status"]).stdout
    assert "Ctrl+C" in runner.invoke(app, ["watch", "stop"]).stdout


def test_reindex_help_is_available() -> None:
    assert runner.invoke(app, ["reindex", "--help"]).exit_code == 0
