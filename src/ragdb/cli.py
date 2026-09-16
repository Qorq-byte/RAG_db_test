"""Command-line entry point for ragdb."""

import typer

from ragdb import __version__

app = typer.Typer(
    name="ragdb",
    help="RAG 个人知识库命令行工具。",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """管理个人知识库。"""


@app.command()
def version() -> None:
    """显示当前版本。"""
    typer.echo(__version__)
