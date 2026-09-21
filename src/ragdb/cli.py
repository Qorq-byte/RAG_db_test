"""Command-line entry point for ragdb."""

from enum import IntEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from ragdb import __version__
from ragdb.application.collections import CollectionService
from ragdb.application.ingestion import IngestionResult, LocalIngestionService
from ragdb.application.metadata import build_ingestion_metadata, build_search_filters
from ragdb.application.sources import SourceService
from ragdb.application.search import SearchService
from ragdb.config import load_settings
from ragdb.domain.errors import ConflictError, NotFoundError, RagdbError, StorageError
from ragdb.infrastructure.chunking import StructuredChunker
from ragdb.infrastructure.embeddings import create_embedding_provider
from ragdb.infrastructure.retrieval import CrossEncoderReranker
from ragdb.infrastructure.database import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteDatabase,
    SQLiteGenerationRepository,
    SQLiteKeywordIndex,
    SQLiteSourceRepository,
    SQLiteTaskRepository,
)
from ragdb.infrastructure.parsers import ParserRegistry
from ragdb.infrastructure.vectorstore import ChromaVectorStore
from ragdb.infrastructure.web import WebCrawler


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
    settings, database = _runtime(ctx)
    vector_store = ChromaVectorStore(
        settings.storage.data_dir / settings.storage.chroma_directory
    )
    return CollectionService(SQLiteCollectionRepository(database), vector_store)


def _runtime(ctx: typer.Context):
    root = ctx.find_root()
    config_path = root.obj.get("config_path", Path("config.toml"))
    settings = load_settings(config_path=config_path)
    database = SQLiteDatabase(
        settings.storage.data_dir / settings.storage.sqlite_filename
    )
    database.initialize()
    return settings, database


def _local_ingestion_service(ctx: typer.Context) -> tuple[LocalIngestionService, SQLiteCollectionRepository]:
    settings, database = _runtime(ctx)
    return (
        LocalIngestionService(
            SQLiteSourceRepository(database),
            SQLiteChunkRepository(database),
            SQLiteTaskRepository(database),
            ParserRegistry(),
            StructuredChunker(settings.chunking),
            SQLiteKeywordIndex(database),
            create_embedding_provider(settings.embedding),
            ChromaVectorStore(settings.storage.data_dir / settings.storage.chroma_directory),
            SQLiteGenerationRepository(database),
        ),
        SQLiteCollectionRepository(database),
    )


def _source_service(ctx: typer.Context) -> tuple[SourceService, SQLiteCollectionRepository]:
    _, database = _runtime(ctx)
    return SourceService(SQLiteSourceRepository(database)), SQLiteCollectionRepository(database)


def _search_service(ctx: typer.Context) -> tuple[SearchService, SQLiteCollectionRepository]:
    settings, database = _runtime(ctx)
    reranker = None
    if settings.rerank.enabled:
        if not settings.rerank.model:
            raise typer.BadParameter("启用重排序时必须配置 rerank.model")
        reranker = CrossEncoderReranker(settings.rerank.model, settings.rerank.batch_size)
    return (
        SearchService(
            create_embedding_provider(settings.embedding),
            ChromaVectorStore(settings.storage.data_dir / settings.storage.chroma_directory),
            SQLiteKeywordIndex(database), SQLiteSourceRepository(database),
            vector_top_k=settings.retrieval.vector_top_k,
            keyword_top_k=settings.retrieval.keyword_top_k,
            result_top_k=settings.retrieval.result_top_k,
            rrf_k=settings.retrieval.rrf_k,
            reranker=reranker,
            rerank_candidate_count=settings.rerank.candidate_count,
        ),
        SQLiteCollectionRepository(database),
    )


def _require_collection(repository: SQLiteCollectionRepository, name: str):
    from ragdb.domain.errors import CollectionNotFoundError

    collection = repository.get_by_name(name)
    if collection is None:
        raise CollectionNotFoundError(name)
    return collection


def _print_ingestion_result(result: IngestionResult) -> None:
    labels = {
        "created": "已导入",
        "updated": "已更新",
        "skipped": "已跳过",
        "failed": "导入失败",
    }
    typer.echo(f"{labels[result.status.value]}：{result.uri}")
    if result.source is not None:
        typer.echo(f"资料 ID：{result.source.id}")
    if result.chunk_count:
        typer.echo(f"文本切片：{result.chunk_count}")
    if result.message:
        typer.echo(f"说明：{result.message}")


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
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="文件路径。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
    tag: Annotated[list[str], typer.Option("--tag", help="资料标签，可重复指定。")] = [],
    course: Annotated[str | None, typer.Option("--course", help="所属课程。")] = None,
    author: Annotated[str | None, typer.Option("--author", help="资料作者。")] = None,
    source_date: Annotated[str | None, typer.Option("--date", help="资料日期（YYYY-MM-DD）。")] = None,
) -> None:
    """导入单个文件。"""

    try:
        service, collections = _local_ingestion_service(ctx)
        result = service.ingest_file(_require_collection(collections, collection), path, build_ingestion_metadata(tags=tuple(tag), course=course, author=author, source_date=source_date))
    except RagdbError as error:
        _exit_for_error(error)
    _print_ingestion_result(result)


@ingest_app.command("directory")
def ingest_directory(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="目录路径。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
    tag: Annotated[list[str], typer.Option("--tag", help="资料标签，可重复指定。")] = [],
    course: Annotated[str | None, typer.Option("--course", help="所属课程。")] = None,
    author: Annotated[str | None, typer.Option("--author", help="资料作者。")] = None,
    source_date: Annotated[str | None, typer.Option("--date", help="资料日期（YYYY-MM-DD）。")] = None,
) -> None:
    """导入目录。"""

    try:
        service, collections = _local_ingestion_service(ctx)
        result = service.ingest_directory(
            _require_collection(collections, collection), path,
            build_ingestion_metadata(tags=tuple(tag), course=course, author=author, source_date=source_date),
        )
    except RagdbError as error:
        _exit_for_error(error)
    for item in result.items:
        _print_ingestion_result(item)
    typer.echo(
        f"任务完成：新增 {result.task.succeeded}，更新 {result.task.updated}，"
        f"跳过 {result.task.skipped}，失败 {result.task.failed}"
    )


@ingest_app.command("text")
def ingest_text(
    ctx: typer.Context,
    text: Annotated[str, typer.Argument(help="要导入的文本。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
    title: Annotated[str, typer.Option("--title", "-t", help="资料标题。")] = "手动文本",
    tag: Annotated[list[str], typer.Option("--tag", help="资料标签，可重复指定。")] = [],
    course: Annotated[str | None, typer.Option("--course", help="所属课程。")] = None,
    author: Annotated[str | None, typer.Option("--author", help="资料作者。")] = None,
    source_date: Annotated[str | None, typer.Option("--date", help="资料日期（YYYY-MM-DD）。")] = None,
) -> None:
    """导入手动输入的文本。"""

    try:
        service, collections = _local_ingestion_service(ctx)
        result = service.ingest_text(
            _require_collection(collections, collection), text, title,
            build_ingestion_metadata(tags=tuple(tag), course=course, author=author, source_date=source_date),
        )
    except RagdbError as error:
        _exit_for_error(error)
    _print_ingestion_result(result)


@app.command()
def crawl(
    ctx: typer.Context,
    url: Annotated[str, typer.Argument(help="起始网页 URL。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """抓取网页并导入集合。"""

    try:
        service, collections = _local_ingestion_service(ctx)
        target = _require_collection(collections, collection)
        settings, _ = _runtime(ctx)
        crawler = WebCrawler(settings.crawl)
        try:
            pages = crawler.crawl(url)
        finally:
            crawler.close()
        for page in pages:
            _print_ingestion_result(service.ingest_web_page(target, page.url, page.title, page.text))
        typer.echo(f"抓取完成：已处理 {len(pages)} 个页面")
    except RagdbError as error:
        _exit_for_error(error)


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
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="检索内容。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
    source_type: Annotated[str | None, typer.Option("--source-type", help="按资料类型筛选。")] = None,
    source_id: Annotated[UUID | None, typer.Option("--source-id", help="按资料 ID 筛选。")] = None,
    tag: Annotated[list[str], typer.Option("--tag", help="按标签筛选，所有标签必须匹配。")] = [],
    course: Annotated[str | None, typer.Option("--course", help="按课程筛选。")] = None,
    author: Annotated[str | None, typer.Option("--author", help="按作者筛选。")] = None,
    date_from: Annotated[str | None, typer.Option("--date-from", help="起始日期（YYYY-MM-DD）。")] = None,
    date_to: Annotated[str | None, typer.Option("--date-to", help="结束日期（YYYY-MM-DD）。")] = None,
) -> None:
    """在指定集合中执行混合检索。"""
    try:
        service, collections = _search_service(ctx)
        filters = build_search_filters(tags=tuple(tag), course=course, author=author, date_from=date_from, date_to=date_to)
        if source_type:
            filters["source_type"] = source_type
        if source_id:
            filters["source_id"] = str(source_id)
        hits = service.search(_require_collection(collections, collection).id, query, filters)
    except (RagdbError, ValueError) as error:
        _exit_for_error(error)
    if not hits:
        typer.echo("未找到匹配资料。")
        return
    for hit in hits:
        typer.echo(f"[{hit.rank}] {hit.source_title} ({', '.join(hit.routes)})")
        typer.echo(hit.text)
        typer.echo(f"出处：{hit.source_uri}")
        position = hit.position
        location: list[str] = []
        if position.page is not None:
            location.append(f"第 {position.page} 页")
        if position.slide is not None:
            location.append(f"第 {position.slide} 张幻灯片")
        if position.line_start is not None:
            end = position.line_end or position.line_start
            location.append(f"第 {position.line_start}-{end} 行")
        if position.heading_path:
            location.append(" / ".join(position.heading_path))
        if location:
            typer.echo(f"位置：{'；'.join(location)}")
        scores = hit.scores
        score_parts = [
            f"语义={scores.semantic:.4f}" if scores.semantic is not None else None,
            f"关键词={scores.keyword:.4f}" if scores.keyword is not None else None,
            f"融合={scores.fusion:.4f}" if scores.fusion is not None else None,
            f"重排序={scores.rerank:.4f}" if scores.rerank is not None else None,
        ]
        typer.echo(f"评分：{', '.join(part for part in score_parts if part)}")


@source_app.command("list")
def source_list(
    ctx: typer.Context,
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """列出集合中的资料。"""

    try:
        service, collections = _source_service(ctx)
        sources = service.list_for_collection(_require_collection(collections, collection))
    except RagdbError as error:
        _exit_for_error(error)
    if not sources:
        typer.echo("暂无资料。")
        return
    typer.echo("标题\t类型\t状态\t代次\tID")
    for source in sources:
        typer.echo(
            f"{source.title}\t{source.source_type.value}\t{source.status.value}\t"
            f"{source.current_generation}\t{source.id}"
        )


@source_app.command("show")
def source_show(
    ctx: typer.Context,
    source_id: Annotated[UUID, typer.Argument(help="资料 ID。")],
) -> None:
    """查看资料详情。"""

    try:
        service, _ = _source_service(ctx)
        source = service.get(source_id)
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(f"标题：{source.title}")
    typer.echo(f"ID：{source.id}")
    typer.echo(f"类型：{source.source_type.value}")
    typer.echo(f"状态：{source.status.value}")
    typer.echo(f"代次：{source.current_generation}")
    typer.echo(f"位置：{source.uri}")
    if source.error_message:
        typer.echo(f"错误：{source.error_message}")


@source_app.command("delete")
def source_delete(
    ctx: typer.Context,
    source_id: Annotated[UUID, typer.Argument(help="资料 ID。")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="跳过删除确认。")] = False,
) -> None:
    """删除资料及其索引。"""

    try:
        service, _ = _source_service(ctx)
        source = service.get(source_id)
        if not yes and not typer.confirm(f"确认删除资料“{source.title}”及其文本索引？"):
            typer.echo("已取消。")
            return
        service.delete(source_id)
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(f"已删除资料：{source.title}")


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
