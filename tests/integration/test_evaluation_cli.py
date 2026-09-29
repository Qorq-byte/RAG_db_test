import json
from importlib.resources import files

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


def test_structured_document_benchmark_parses_markdown_docx_and_pdf(tmp_path):
    dataset = files("ragdb").joinpath("evaluation_data/complex_documents.json")
    output = tmp_path / "structured-report.json"
    result = CliRunner().invoke(app, ["evaluate", "run", str(output), "--dataset", str(dataset), "--offline"])
    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dataset"] == "ragdb-structured-documents-v1"
    assert report["query_count"] == 8
    assert report["passed"]
    assert report["metrics"]["recall"] >= .8
    assert report["metrics"]["mrr"] >= .75
    assert {query["id"] for query in report["queries"]} == {
        "markdown_heading", "markdown_failure", "word_paragraph", "word_table",
        "pdf_checksum", "pdf_credential", "secret_storage", "chunk_overlap",
    }
