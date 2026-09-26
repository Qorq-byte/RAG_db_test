"""Reproducible retrieval evaluation without changing the user's library."""

from importlib.resources import files
import json
from pathlib import Path
import tempfile

import typer

from ragdb.application.evaluation import benchmark, evaluate
from ragdb.config import load_settings


app = typer.Typer(help="运行检索质量评估并导出JSON报告。", no_args_is_help=True)


@app.command("run")
def run(ctx: typer.Context, output: Path, dataset: Path | None = None,
        collection: str | None = None, offline: bool = False,
        k: int = typer.Option(3, min=1), min_recall: float = typer.Option(.8, min=0, max=1),
        min_mrr: float = typer.Option(.75, min=0, max=1)):
    """默认在临时库评估内置资料；--collection 只查询指定现有集合。"""
    if output.exists():
        raise typer.BadParameter("报告已存在，请指定新的输出文件。")
    if collection and (dataset is None or offline):
        raise typer.BadParameter("现有集合评估需要 --dataset，且不能使用 --offline。")
    data = json.loads(dataset.read_text(encoding="utf-8") if dataset else
                      files("ragdb").joinpath("evaluation_data/benchmark.json").read_text(encoding="utf-8"))
    settings = load_settings(config_path=ctx.find_root().obj["config_path"])
    if collection:
        from ragdb.runtime import ApplicationRuntime
        runtime = ApplicationRuntime.from_config(ctx.find_root().obj["config_path"])
        stored = runtime.collections.get_by_name(collection)
        if stored is None:
            raise typer.BadParameter("集合不存在。")
        service = runtime.search_service()
        service.result_top_k = max(service.result_top_k, k)
        report = evaluate(data, lambda query, filters: service.search(stored.id, query, filters),
                          k=k, min_recall=min_recall, min_mrr=min_mrr)
        report["scope"] = "existing library labelled queries"
    else:
        with tempfile.TemporaryDirectory(prefix="ragdb-evaluation-") as directory:
            report = benchmark(data, settings, Path(directory), offline=offline,
                               k=k, min_recall=min_recall, min_mrr=min_mrr)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    typer.echo(json.dumps({"passed": report["passed"], "metrics": report["metrics"], "report": str(output)}, ensure_ascii=False))
    if not report["passed"]:
        raise typer.Exit(1)
