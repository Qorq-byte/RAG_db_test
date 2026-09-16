from typer.testing import CliRunner

from ragdb import __version__
from ragdb.cli import app


runner = CliRunner()


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_help_is_available() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "RAG 个人知识库命令行工具" in result.stdout


def test_cli_version_command() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
