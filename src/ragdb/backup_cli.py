"""Backup commands kept separate from the general CLI."""

import json
from pathlib import Path
import typer

from ragdb.application.backup import BackupService
from ragdb.config import load_settings
from ragdb.domain.errors import RagdbError


app = typer.Typer(help="创建、校验和恢复全库备份。", no_args_is_help=True)


def _run(function):
    try:
        result = function()
    except (RagdbError, OSError, ValueError, KeyError) as error:
        typer.echo(f"备份操作失败：{error}", err=True)
        raise typer.Exit(6) from error
    typer.echo(json.dumps(result, ensure_ascii=False, default=str))


@app.command("create")
def create(ctx: typer.Context, output: Path):
    settings = load_settings(config_path=ctx.find_root().obj["config_path"])
    _run(lambda: BackupService(settings).create(output))


@app.command("verify")
def verify(archive: Path):
    _run(lambda: BackupService.verify(archive))


@app.command("restore")
def restore(archive: Path, destination: Path):
    """恢复到尚不存在的新目录，返回可使用的 config.toml。"""
    _run(lambda: {"config": BackupService.restore(archive, destination)})
