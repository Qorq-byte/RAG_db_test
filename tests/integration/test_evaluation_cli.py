import json

from typer.testing import CliRunner

from ragdb.cli import app


def test_offline_benchmark_uses_isolated_library_and_reports_metrics(tmp_path):
    output = tmp_path / "report.json"
    result = CliRunner().invoke(app, ["evaluate", "run", str(output), "--offline"])
    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["query_count"] == 16
    assert report["passed"]
    assert report["scope"] == "offline pipeline smoke test"
    assert report["metrics"]["recall"] >= .8
    before = output.read_bytes()
    result = CliRunner().invoke(app, ["evaluate", "run", str(output), "--offline"])
    assert result.exit_code == 2
    assert output.read_bytes() == before
