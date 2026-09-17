"""Command-line entry point for ragdb."""

from enum import IntEnum
from pathlib import Path
from typing import Annotated

import typer

from ragdb import __version__
from ragdb.application.collections import CollectionService
from ragdb.config import load_settings
from ragdb.domain.errors import ConflictError, NotFoundError, RagdbError, StorageError
from ragdb.infrastructure.database import SQLiteCollectionRepository, SQLiteDatabase
from ragdb.infrastructure.vectorstore import ChromaVectorStore


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE_ERROR = 2
    NOT_IMPLEMENTED = 3
    NOT_FOUND = 4
    CONFLICT = 5
    STORAGE_ERROR = 6


app = typer.Typer(
    name="ragdb",
    help="RAG 个人知识库命令行工具。",
    no_args_is_help=True,
)
collection_app = typer.Typer(help="创建和管理知识集合。", no_args_is_help=True)
ingest_app = typer.Typer(help="导入本地资料或文本。", no_args_is_help=True)
watch_app = typer.Typer(help="监听目录并同步索引。", no_args_is_help=True)
source_app = typer.Typer(help="查看和管理资料来源。", no_args_is_help=True)

app.add_typer(collection_app, name="collection")
app.add_typer(ingest_app, name="ingest")
app.add_typer(watch_app, name="watch")
app.add_typer(source_app, name="source")


def _pending(feature: str) -> None:
    typer.echo(f"{feature} 尚未实现，将在后续里程碑中提供。", err=True)
    raise typer.Exit(code=ExitCode.NOT_IMPLEMENTED)


def _collection_service(ctx: typer.Context) -> CollectionService:
    root = ctx.find_root()
    config_path = root.obj.get("config_path", Path("config.toml"))
    settings = load_settings(config_path=config_path)
    database = SQLiteDatabase(
        settings.storage.data_dir / settings.storage.sqlite_filename
    )
    database.initialize()
    vector_store = ChromaVectorStore(
        settings.storage.data_dir / settings.storage.chroma_directory
    )
    return CollectionService(SQLiteCollectionRepository(database), vector_store)


def _exit_for_error(error: RagdbError) -> None:
    typer.echo(str(error), err=True)
    if isinstance(error, NotFoundError):
        code = ExitCode.NOT_FOUND
    elif isinstance(error, ConflictError):
        code = ExitCode.CONFLICT
    elif isinstance(error, StorageError):
        code = ExitCode.STORAGE_ERROR
    else:
        code = ExitCode.USAGE_ERROR
    raise typer.Exit(code=code)


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path,
        typer.Option("--config", help="TOML 配置文件路径。"),
    ] = Path("config.toml"),
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="输出详细日志。"),
    ] = False,
) -> None:
    """管理个人知识库。"""

    ctx.ensure_object(dict)
    ctx.obj.update(config_path=config, verbose=verbose)


@app.command()
def version() -> None:
    """显示当前版本。"""

    typer.echo(__version__)


@app.command("init")
def init_project() -> None:
    """初始化本地知识库数据目录。"""

    _pending("初始化")


@collection_app.command("create")
def collection_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="集合名称。")],
    description: Annotated[
        str | None,
        typer.Option("--description", "-d", help="集合说明。"),
    ] = None,
) -> None:
    """创建知识集合。"""

    try:
        collection = _collection_service(ctx).create(name, description)
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(f"已创建知识集合：{collection.name}")
    typer.echo(f"ID：{collection.id}")


@collection_app.command("list")
def collection_list(ctx: typer.Context) -> None:
    """列出知识集合。"""

    try:
        collections = _collection_service(ctx).list_all()
    except RagdbError as error:
        _exit_for_error(error)
    if not collections:
        typer.echo("暂无知识集合。")
        return
    typer.echo("名称\tID\t说明")
    for collection in collections:
        typer.echo(
            f"{collection.name}\t{collection.id}\t{collection.description or '-'}"
        )


@collection_app.command("info")
def collection_info(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="集合名称。")],
) -> None:
    """查看集合详情。"""

    try:
        collection = _collection_service(ctx).get_by_name(name)
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(f"名称：{collection.name}")
    typer.echo(f"ID：{collection.id}")
    typer.echo(f"说明：{collection.description or '-'}")
    typer.echo(f"创建时间：{collection.created_at.isoformat()}")
    typer.echo(f"更新时间：{collection.updated_at.isoformat()}")


@collection_app.command("delete")
def collection_delete(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="集合名称。")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="跳过删除确认。"),
    ] = False,
) -> None:
    """删除知识集合。"""

    try:
        service = _collection_service(ctx)
        collection = service.get_by_name(name)
        if not yes and not typer.confirm(
            f"确认删除知识集合“{collection.name}”及其全部索引？"
        ):
            typer.echo("已取消。")
            return
        service.delete_by_name(name)
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(f"已删除知识集合：{collection.name}")


@ingest_app.command("file")
def ingest_file(
    path: Annotated[Path, typer.Argument(help="文件路径。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """导入单个文件。"""

    _pending(f"导入文件 {path} 到 {collection}")


@ingest_app.command("directory")
def ingest_directory(
    path: Annotated[Path, typer.Argument(help="目录路径。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """导入目录。"""

    _pending(f"导入目录 {path} 到 {collection}")


@ingest_app.command("text")
def ingest_text(
    text: Annotated[str, typer.Argument(help="要导入的文本。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """导入手动输入的文本。"""

    _pending(f"导入文本到 {collection}: {text[:20]}")


@app.command()
def crawl(
    url: Annotated[str, typer.Argument(help="起始网页 URL。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """抓取网页并导入集合。"""

    _pending(f"抓取 {url} 到 {collection}")


@app.command("repo")
def import_repository(
    url: Annotated[str, typer.Argument(help="公开 GitHub 仓库 URL。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """导入公开 GitHub 仓库。"""

    _pending(f"导入仓库 {url} 到 {collection}")


@watch_app.command("start")
def watch_start(
    path: Annotated[Path, typer.Argument(help="监听目录。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """启动目录监听。"""

    _pending(f"监听 {path} 并同步到 {collection}")


@watch_app.command("status")
def watch_status() -> None:
    """查看目录监听状态。"""

    _pending("监听状态")


@watch_app.command("stop")
def watch_stop() -> None:
    """停止目录监听。"""

    _pending("停止监听")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="检索内容。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """在指定集合中执行混合检索。"""

    _pending(f"在 {collection} 中检索 {query}")


@source_app.command("list")
def source_list(
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """列出集合中的资料。"""

    _pending(f"列出 {collection} 的资料")


@source_app.command("show")
def source_show(source_id: Annotated[str, typer.Argument(help="资料 ID。")]) -> None:
    """查看资料详情。"""

    _pending(f"资料详情 {source_id}")


@source_app.command("delete")
def source_delete(source_id: Annotated[str, typer.Argument(help="资料 ID。")]) -> None:
    """删除资料及其索引。"""

    _pending(f"删除资料 {source_id}")


@app.command()
def reindex(
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """重建指定集合的索引。"""

    _pending(f"重建 {collection} 的索引")


@app.command()
def doctor() -> None:
    """检查配置与运行环境。"""

    _pending("环境诊断")
