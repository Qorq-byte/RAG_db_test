"""Command-line entry point for ragdb."""

from enum import IntEnum
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Annotated
from uuid import UUID

import typer

from ragdb import __version__
from ragdb.application.collections import CollectionService
from ragdb.application.ingestion import IngestionResult, LocalIngestionService, iter_supported_files
from ragdb.application.metadata import build_ingestion_metadata, build_search_filters
from ragdb.application.sources import SourceService
from ragdb.application.search import SearchService
from ragdb.application.chat import AnswerService
from ragdb.config import load_settings
from ragdb.diagnostics import DiagnosticStatus, has_failures, run_diagnostics
from ragdb.domain.errors import ConflictError, NotFoundError, RagdbError, StorageError
from ragdb.infrastructure.chunking import StructuredChunker
from ragdb.infrastructure.embeddings import create_embedding_provider
from ragdb.infrastructure.retrieval import CrossEncoderReranker
from ragdb.infrastructure.database import (
    SQLiteChunkRepository,
    SQLiteCollectionRepository,
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteGenerationRepository,
    SQLiteOperationLogRepository,
    SQLiteKeywordIndex,
    SQLiteSourceRepository,
    SQLiteTaskRepository,
)
from ragdb.domain.models import OperationLog
from ragdb.logging import configure_logging
from ragdb.infrastructure.parsers import ParserRegistry
from ragdb.infrastructure.parsers.ocr import TesseractOcr
from ragdb.infrastructure.vectorstore import ChromaVectorStore
from ragdb.infrastructure.web import WebCrawler
from ragdb.infrastructure.github import PublicGitHubImporter
from ragdb.infrastructure.watcher import DebouncedPathEvents, start_observer
from ragdb.infrastructure.chat import create_chat_model
import time


class ExitCode(IntEnum):
    SUCCESS = 0
    DOCTOR_FAILED = 1
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
task_app = typer.Typer(help="查看批量导入任务。", no_args_is_help=True)
log_app = typer.Typer(help="查看操作日志。", no_args_is_help=True)
chat_app = typer.Typer(help="基于集合资料进行多轮问答。", no_args_is_help=True)
chat_session_app = typer.Typer(help="管理持久化问答会话。", no_args_is_help=True)

app.add_typer(collection_app, name="collection")
app.add_typer(ingest_app, name="ingest")
app.add_typer(watch_app, name="watch")
app.add_typer(source_app, name="source")
app.add_typer(task_app, name="task")
app.add_typer(log_app, name="log")
app.add_typer(chat_app, name="chat")
chat_app.add_typer(chat_session_app, name="session")


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
    sensitive_values = []
    if settings.embedding.cloud_api_key is not None:
        sensitive_values.append(settings.embedding.cloud_api_key.get_secret_value())
    if settings.chat.cloud_api_key is not None:
        sensitive_values.append(settings.chat.cloud_api_key.get_secret_value())
    configure_logging(settings.log_level, settings.storage.data_dir / "logs" / "ragdb.log", sensitive_values)
    database = SQLiteDatabase(
        settings.storage.data_dir / settings.storage.sqlite_filename
    )
    database.initialize()
    return settings, database


def _record_operation(
    ctx: typer.Context, action: str, *, collection_id: UUID | None = None,
    source_id: UUID | None = None, details: dict[str, object] | None = None,
) -> None:
    _, database = _runtime(ctx)
    SQLiteOperationLogRepository(database).record(
        OperationLog(collection_id=collection_id, source_id=source_id, action=action, details=details or {})
    )


def _local_ingestion_service(ctx: typer.Context) -> tuple[LocalIngestionService, SQLiteCollectionRepository]:
    settings, database = _runtime(ctx)
    return (
        LocalIngestionService(
            SQLiteSourceRepository(database),
            SQLiteChunkRepository(database),
            SQLiteTaskRepository(database),
            ParserRegistry(ocr=_ocr(settings)),
            StructuredChunker(settings.chunking),
            SQLiteKeywordIndex(database),
            create_embedding_provider(settings.embedding),
            ChromaVectorStore(settings.storage.data_dir / settings.storage.chroma_directory),
            SQLiteGenerationRepository(database),
        ),
        SQLiteCollectionRepository(database),
    )


def _source_service(ctx: typer.Context) -> tuple[SourceService, SQLiteCollectionRepository]:
    settings, database = _runtime(ctx)
    return (
        SourceService(
            SQLiteSourceRepository(database),
            ChromaVectorStore(settings.storage.data_dir / settings.storage.chroma_directory),
        ),
        SQLiteCollectionRepository(database),
    )


def _ocr(settings):
    if not settings.ocr.enabled or settings.ocr.executable_path is None:
        return None
    return TesseractOcr(settings.ocr.executable_path, settings.ocr.languages, settings.ocr.dpi)


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
def init_project(ctx: typer.Context) -> None:
    """初始化本地知识库数据目录。"""
    root = ctx.find_root()
    config_path = root.obj.get("config_path", Path("config.toml"))
    settings = load_settings(config_path=config_path)
    was_initialized = settings.storage.data_dir.exists()
    _, database = _runtime(ctx)
    (settings.storage.data_dir / settings.storage.chroma_directory).mkdir(parents=True, exist_ok=True)
    _record_operation(ctx, "initialize", details={"data_dir": str(settings.storage.data_dir)})
    state = "已存在" if was_initialized else "已创建"
    typer.echo(f"知识库已初始化：{settings.storage.data_dir}（{state}）")
    typer.echo(f"SQLite：{database.path}")


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
    _record_operation(ctx, "collection_created", collection_id=collection.id, details={"name": collection.name})


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
    _record_operation(ctx, "collection_deleted", details={"name": collection.name, "collection_id": str(collection.id)})


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
    if result.source is not None:
        _record_operation(ctx, "source_ingested", collection_id=result.source.collection_id, source_id=result.source.id, details={"status": result.status.value})


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
        completed = 0
        total = len(iter_supported_files(path))
        def report_progress(item: IngestionResult) -> None:
            nonlocal completed
            completed += 1
            _print_ingestion_result(item)
            typer.echo(f"进度：{completed}/{total}")
        result = service.ingest_directory(
            _require_collection(collections, collection), path,
            build_ingestion_metadata(tags=tuple(tag), course=course, author=author, source_date=source_date),
            on_item=report_progress,
        )
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(
        f"任务完成：新增 {result.task.succeeded}，更新 {result.task.updated}，"
        f"跳过 {result.task.skipped}，失败 {result.task.failed}"
    )
    _record_operation(ctx, "directory_ingested", collection_id=result.task.collection_id, details={"task_id": str(result.task.id)})


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
    if result.source is not None:
        _record_operation(ctx, "source_ingested", collection_id=result.source.collection_id, source_id=result.source.id, details={"status": result.status.value})


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
    ctx: typer.Context,
    url: Annotated[str, typer.Argument(help="公开 GitHub 仓库 URL。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """导入公开 GitHub 仓库。"""

    try:
        service, collections = _local_ingestion_service(ctx)
        settings, _ = _runtime(ctx)
        target = _require_collection(collections, collection)
        importer = PublicGitHubImporter(
            settings.storage.data_dir / "cache" / "repos", service.max_file_size_bytes
        )
        _, files = importer.clone_and_list(url)
        for item in files:
            _print_ingestion_result(service.ingest_file(target, item.path, {
                "repository_url": item.repository_url, "repository_path": item.relative_path,
            }))
        typer.echo(f"仓库导入完成：已处理 {len(files)} 个文件")
    except RagdbError as error:
        _exit_for_error(error)


@watch_app.command("start")
def watch_start(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="监听目录。")],
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """启动目录监听。"""

    try:
        service, collections = _local_ingestion_service(ctx)
        target = _require_collection(collections, collection)
        if not path.is_dir():
            raise typer.BadParameter("监听目录不存在")
        events = DebouncedPathEvents(0.5, time.monotonic)
        observer = start_observer(path, events)
        typer.echo(f"正在监听：{path.resolve()}（按 Ctrl+C 停止）")
        try:
            while True:
                for event_path, operation in events.ready():
                    if operation == "upsert" and event_path.exists():
                        _print_ingestion_result(service.ingest_file(target, event_path))
                    elif operation == "delete":
                        source = service.source_repository.get_by_uri(target.id, event_path.resolve().as_uri())
                        if source is not None:
                            SourceService(service.source_repository, service.vector_store).delete(source.id)
                            typer.echo(f"已删除资料：{event_path}")
                time.sleep(0.2)
        except KeyboardInterrupt:
            typer.echo("已停止监听。")
        finally:
            observer.stop(); observer.join()
    except RagdbError as error:
        _exit_for_error(error)


@watch_app.command("status")
def watch_status() -> None:
    """查看目录监听状态。"""

    typer.echo("前台监听仅在运行 `ragdb watch start` 的终端中生效。")


@watch_app.command("stop")
def watch_stop() -> None:
    """停止目录监听。"""

    typer.echo("请在运行 `ragdb watch start` 的终端按 Ctrl+C 停止监听。")


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


@chat_app.command("ask")
def chat_ask(ctx: typer.Context, question: Annotated[str, typer.Argument()], collection: Annotated[str, typer.Option("--collection", "-c")], session: Annotated[UUID | None, typer.Option("--session")] = None) -> None:
    """依据检索到的资料回答问题。"""
    try:
        settings, database = _runtime(ctx)
        search_service, collections = _search_service(ctx)
        service = AnswerService(search_service, create_chat_model(settings.chat), SQLiteConversationRepository(database), evidence_limit=settings.chat.evidence_limit, evidence_character_budget=settings.chat.evidence_character_budget, history_character_budget=settings.chat.history_character_budget)
        result = service.ask(_require_collection(collections, collection).id, question, session)
    except (RagdbError, RuntimeError, ValueError) as error:
        _exit_for_error(error)
    typer.echo(f"会话 ID：{result.conversation.id}")
    typer.echo(result.content)
    for citation in result.citations:
        typer.echo(f"[{citation.display_index}] {citation.source_title}：{citation.source_uri}")


@chat_session_app.command("list")
def chat_session_list(ctx: typer.Context, collection: Annotated[str, typer.Option("--collection", "-c")]) -> None:
    """列出集合内的问答会话。"""
    _, database = _runtime(ctx)
    target = _require_collection(SQLiteCollectionRepository(database), collection)
    sessions = SQLiteConversationRepository(database).list_for_collection(target.id)
    for item in sessions:
        typer.echo(f"{item.id}\t{item.title or '-'}\t{item.updated_at.isoformat()}")


@chat_session_app.command("show")
def chat_session_show(ctx: typer.Context, session_id: Annotated[UUID, typer.Argument()], collection: Annotated[str, typer.Option("--collection", "-c")]) -> None:
    """显示一个会话及其消息。"""
    _, database = _runtime(ctx)
    target = _require_collection(SQLiteCollectionRepository(database), collection)
    repository = SQLiteConversationRepository(database)
    session = repository.get(session_id)
    if session is None or session.collection_id != target.id:
        _exit_for_error(NotFoundError("指定会话不存在于该知识集合"))
    for message in repository.list_messages(session_id):
        typer.echo(f"{message.role.value}：{message.content}")


@chat_session_app.command("delete")
def chat_session_delete(ctx: typer.Context, session_id: Annotated[UUID, typer.Argument()], collection: Annotated[str, typer.Option("--collection", "-c")], yes: Annotated[bool, typer.Option("--yes", "-y")] = False) -> None:
    """删除一个问答会话。"""
    _, database = _runtime(ctx)
    target = _require_collection(SQLiteCollectionRepository(database), collection)
    repository = SQLiteConversationRepository(database)
    session = repository.get(session_id)
    if session is None or session.collection_id != target.id:
        _exit_for_error(NotFoundError("指定会话不存在于该知识集合"))
    if not yes and not typer.confirm("确认删除该问答会话？"):
        typer.echo("已取消。")
        return
    repository.delete(session_id)
    typer.echo("已删除问答会话。")


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
    _record_operation(ctx, "source_deleted", collection_id=source.collection_id, details={"title": source.title, "source_id": str(source.id)})


@task_app.command("list")
def task_list(
    ctx: typer.Context,
    collection: Annotated[str, typer.Option("--collection", "-c")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    """列出集合最近的批量导入任务。"""

    try:
        _, database = _runtime(ctx)
        target = _require_collection(SQLiteCollectionRepository(database), collection)
        tasks = SQLiteTaskRepository(database).list_for_collection(target.id, limit)
    except RagdbError as error:
        _exit_for_error(error)
    if not tasks:
        typer.echo("暂无批量导入任务。")
        return
    typer.echo("ID\t状态\t开始时间\t新增\t更新\t跳过\t失败")
    for task in tasks:
        typer.echo(
            f"{task.id}\t{task.status.value}\t{task.started_at.isoformat()}\t{task.succeeded}\t"
            f"{task.updated}\t{task.skipped}\t{task.failed}"
        )


@task_app.command("show")
def task_show(ctx: typer.Context, task_id: Annotated[UUID, typer.Argument(help="任务 ID。")]) -> None:
    """查看一个批量导入任务的统计信息。"""

    try:
        _, database = _runtime(ctx)
        task = SQLiteTaskRepository(database).get(task_id)
        if task is None:
            from ragdb.domain.errors import TaskNotFoundError
            raise TaskNotFoundError(task_id)
    except RagdbError as error:
        _exit_for_error(error)
    typer.echo(f"ID：{task.id}")
    typer.echo(f"集合 ID：{task.collection_id}")
    typer.echo(f"状态：{task.status.value}")
    typer.echo(f"开始时间：{task.started_at.isoformat()}")
    typer.echo(f"结束时间：{task.finished_at.isoformat() if task.finished_at else '-'}")
    typer.echo(f"新增：{task.succeeded}，更新：{task.updated}，跳过：{task.skipped}，失败：{task.failed}")


@log_app.command("list")
def log_list(
    ctx: typer.Context,
    collection: Annotated[str | None, typer.Option("--collection", "-c")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    """查看最新操作日志。"""

    try:
        _, database = _runtime(ctx)
        collection_id = None
        if collection is not None:
            collection_id = _require_collection(SQLiteCollectionRepository(database), collection).id
        logs = SQLiteOperationLogRepository(database).list_recent(collection_id, limit)
    except RagdbError as error:
        _exit_for_error(error)
    if not logs:
        typer.echo("暂无操作日志。")
        return
    typer.echo("时间\t操作\t集合 ID\t资料 ID\t详情")
    for entry in logs:
        typer.echo(
            f"{entry.created_at.isoformat()}\t{entry.action}\t{entry.collection_id or '-'}\t"
            f"{entry.source_id or '-'}\t{entry.details}"
        )


@app.command()
def reindex(
    ctx: typer.Context,
    collection: Annotated[str, typer.Option("--collection", "-c")],
) -> None:
    """重建指定集合的索引。"""
    try:
        service, collections = _local_ingestion_service(ctx)
        service.allow_configuration_change = True
        target = _require_collection(collections, collection)
        items = []
        for source in service.source_repository.list_for_collection(target.id):
            if source.uri.startswith("file://"):
                parsed = urlparse(source.uri)
                source_path = Path(unquote(parsed.path.lstrip("/")))
                try:
                    items.append(service.ingest_file(target, source_path, source.metadata))
                except RagdbError as error:
                    typer.echo(f"重建失败：{source.uri}；{error}", err=True)
        for item in items:
            _print_ingestion_result(item)
        typer.echo(f"重建完成：已处理 {len(items)} 个本地资料")
        _record_operation(ctx, "collection_reindexed", collection_id=target.id, details={"processed": len(items)})
    except RagdbError as error:
        _exit_for_error(error)


@app.command()
def doctor(ctx: typer.Context) -> None:
    """检查配置与运行环境。"""

    root = ctx.find_root()
    config_path = root.obj.get("config_path", Path("config.toml"))
    results = run_diagnostics(config_path)
    for result in results:
        typer.echo(f"[{result.status.value}] {result.name}：{result.detail}")
        if result.status is not DiagnosticStatus.PASS and result.remedy:
            typer.echo(f"  建议：{result.remedy}")
    if has_failures(results):
        raise typer.Exit(code=ExitCode.DOCTOR_FAILED)
