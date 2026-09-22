from pathlib import Path

from typer.testing import CliRunner

import ragdb.cli as cli
from ragdb.diagnostics import DiagnosticResult, DiagnosticStatus, has_failures


runner = CliRunner()


def test_has_failures_only_for_failure_results() -> None:
    results = [
        DiagnosticResult("配置", DiagnosticStatus.PASS, "已加载"),
        DiagnosticResult("Git", DiagnosticStatus.WARNING, "未安装"),
    ]

    assert not has_failures(results)
    assert has_failures([*results, DiagnosticResult("FTS5", DiagnosticStatus.FAILURE, "缺失")])


def test_doctor_warns_without_failing(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_diagnostics",
        lambda _: [DiagnosticResult("配置解析", DiagnosticStatus.WARNING, "使用默认值", "创建配置文件")],
    )

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "[警告] 配置解析：使用默认值" in result.stdout
    assert "建议：创建配置文件" in result.stdout


def test_doctor_failure_has_nonzero_exit_code(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_diagnostics",
        lambda _: [DiagnosticResult("SQLite FTS5", DiagnosticStatus.FAILURE, "缺失", "更换 Python")],
    )

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == cli.ExitCode.DOCTOR_FAILED
    assert "[失败] SQLite FTS5：缺失" in result.stdout


def test_doctor_receives_global_config_option(monkeypatch) -> None:
    received: list[Path] = []
    monkeypatch.setattr(cli, "run_diagnostics", lambda path: received.append(path) or [])

    result = runner.invoke(cli.app, ["--config", "example.toml", "doctor"])

    assert result.exit_code == 0
    assert received == [Path("example.toml")]
