from pathlib import Path
from uuid import UUID

from click.testing import Result
from typer.testing import CliRunner

from ragdb.cli import ExitCode, app
from ragdb.domain.models import Chunk
from ragdb.infrastructure.vectorstore import ChromaVectorStore


runner = CliRunner()


def write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[storage]",
                f'data_dir = "{tmp_path.as_posix()}/data"',
                'sqlite_filename = "catalog.sqlite3"',
                'chroma_directory = "chroma"',
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def invoke(
    config_path: Path,
    *arguments: str,
    input: str | None = None,
) -> Result:
    return runner.invoke(
        app,
        ["--config", str(config_path), *arguments],
        input=input,
    )


def test_collection_list_reports_empty_catalog(tmp_path: Path) -> None:
    result = invoke(write_config(tmp_path), "collection", "list")

    assert result.exit_code == ExitCode.SUCCESS
    assert "暂无知识集合" in result.output


def test_collection_commands_persist_across_invocations(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)

    created = invoke(
        config_path,
        "collection",
        "create",
        "论文",
        "--description",
        "论文资料",
    )
    listed = invoke(config_path, "collection", "list")
    info = invoke(config_path, "collection", "info", "论文")

    assert created.exit_code == ExitCode.SUCCESS
    assert "已创建知识集合：论文" in created.output
    assert listed.exit_code == ExitCode.SUCCESS
    assert "论文" in listed.output
    assert "论文资料" in listed.output
    assert info.exit_code == ExitCode.SUCCESS
    assert "名称：论文" in info.output
    assert "说明：论文资料" in info.output


def test_collection_create_rejects_duplicate_name(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    assert invoke(config_path, "collection", "create", "课程").exit_code == 0

    duplicate = invoke(config_path, "collection", "create", "课程")

    assert duplicate.exit_code == ExitCode.CONFLICT
    assert "知识集合已存在" in duplicate.output


def test_collection_info_reports_missing_collection(tmp_path: Path) -> None:
    result = invoke(write_config(tmp_path), "collection", "info", "不存在")

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "知识集合不存在" in result.output


def test_collection_delete_can_be_cancelled(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    assert invoke(config_path, "collection", "create", "课程").exit_code == 0

    cancelled = invoke(
        config_path,
        "collection",
        "delete",
        "课程",
        input="n\n",
    )

    assert cancelled.exit_code == ExitCode.SUCCESS
    assert "已取消" in cancelled.output
    assert invoke(config_path, "collection", "info", "课程").exit_code == 0


def test_collection_delete_reports_missing_collection(tmp_path: Path) -> None:
    result = invoke(
        write_config(tmp_path),
        "collection",
        "delete",
        "不存在",
        "--yes",
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "知识集合不存在" in result.output


def test_collection_delete_removes_sqlite_and_chroma_data(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    created = invoke(config_path, "collection", "create", "课程")
    collection_id = UUID(created.output.split("ID：", maxsplit=1)[1].strip())
    source_id = UUID("12345678-1234-5678-1234-567812345678")
    chunk = Chunk(
        id="chunk-1",
        collection_id=collection_id,
        source_id=source_id,
        source_content_hash="a" * 64,
        generation=1,
        ordinal=0,
        text="测试",
        normalized_text="测试",
    )
    store = ChromaVectorStore(tmp_path / "data" / "chroma")
    store.upsert([chunk], [[1.0, 0.0]])

    deleted = invoke(config_path, "collection", "delete", "课程", "--yes")

    assert deleted.exit_code == ExitCode.SUCCESS
    assert "已删除知识集合：课程" in deleted.output
    assert invoke(config_path, "collection", "info", "课程").exit_code == ExitCode.NOT_FOUND
    assert store.search(collection_id, [1.0, 0.0], limit=5) == []
