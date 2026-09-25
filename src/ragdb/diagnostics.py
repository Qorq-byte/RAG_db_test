"""Non-destructive runtime checks used by the ``ragdb doctor`` command."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import importlib
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from ragdb.config import AppSettings, load_settings


class DiagnosticStatus(str, Enum):
    """The severity of a doctor check."""

    PASS = "通过"
    WARNING = "警告"
    FAILURE = "失败"


@dataclass(frozen=True)
class DiagnosticResult:
    """One independently reportable environment check."""

    name: str
    status: DiagnosticStatus
    detail: str
    remedy: str | None = None


def run_diagnostics(config_path: Path) -> list[DiagnosticResult]:
    """Inspect the local environment without contacting services or loading models."""

    results = [_check_python_version(), _check_configuration(config_path)]
    configuration = results[-1]
    if configuration.status is DiagnosticStatus.FAILURE:
        return results

    settings = load_settings(config_path=config_path)
    results.extend(
        (
            _check_data_directory(settings),
            _check_sqlite_fts5(),
            _check_python_package("ChromaDB", "chromadb", required=True),
            _check_git(),
            _check_local_embedding_dependency(settings),
            _check_ollama_embedding_configuration(settings),
            _check_cloud_embedding_configuration(settings),
            _check_chat_configuration(settings),
            _check_ocr(settings),
        )
    )
    return results


def has_failures(results: list[DiagnosticResult]) -> bool:
    """Return whether the report contains a blocking problem."""

    return any(result.status is DiagnosticStatus.FAILURE for result in results)


def _check_python_version() -> DiagnosticResult:
    version = sys.version_info
    supported = (3, 11) <= (version.major, version.minor) < (3, 12)
    if supported:
        return DiagnosticResult("Python 版本", DiagnosticStatus.PASS, f"{version.major}.{version.minor}.{version.micro}")
    return DiagnosticResult(
        "Python 版本",
        DiagnosticStatus.FAILURE,
        f"当前为 {version.major}.{version.minor}.{version.micro}，项目要求 >=3.11,<3.12。",
        "请使用 Python 3.11 创建并激活虚拟环境。",
    )


def _check_configuration(config_path: Path) -> DiagnosticResult:
    try:
        load_settings(config_path=config_path)
    except Exception as error:  # Pydantic exposes several validation exception types.
        return DiagnosticResult(
            "配置解析",
            DiagnosticStatus.FAILURE,
            f"无法加载 {config_path}: {error}",
            "请根据 config.example.toml 修正配置，并将云端密钥放在 .env 或环境变量中。",
        )
    if config_path.exists():
        return DiagnosticResult("配置解析", DiagnosticStatus.PASS, f"已加载 {config_path}。")
    return DiagnosticResult(
        "配置解析",
        DiagnosticStatus.WARNING,
        f"未找到 {config_path}，正在使用默认值和环境变量。",
        "复制 config.example.toml 为 config.toml，再按需调整配置。",
    )


def _check_data_directory(settings: AppSettings) -> DiagnosticResult:
    data_dir = settings.storage.data_dir
    if data_dir.exists() and not data_dir.is_dir():
        return DiagnosticResult(
            "数据目录可写",
            DiagnosticStatus.FAILURE,
            f"{data_dir} 已存在但不是目录。",
            "修改 storage.data_dir，使其指向可写目录。",
        )

    probe_dir = data_dir if data_dir.exists() else _nearest_existing_parent(data_dir)
    try:
        with tempfile.NamedTemporaryFile(dir=probe_dir):
            pass
    except OSError as error:
        return DiagnosticResult(
            "数据目录可写",
            DiagnosticStatus.FAILURE,
            f"无法在 {probe_dir} 创建临时权限探测文件: {error}",
            "修正 storage.data_dir 或授予该目录写入权限。",
        )

    if data_dir.exists():
        return DiagnosticResult("数据目录可写", DiagnosticStatus.PASS, f"{data_dir} 可写。")
    return DiagnosticResult(
        "数据目录可写",
        DiagnosticStatus.WARNING,
        f"{data_dir} 尚未创建，但父目录 {probe_dir} 可写。",
        "首次创建集合时会建立该目录；也可手动创建后再次运行 doctor。",
    )


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _check_sqlite_fts5() -> DiagnosticResult:
    try:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE VIRTUAL TABLE doctor_fts USING fts5(content)")
    except sqlite3.Error as error:
        return DiagnosticResult(
            "SQLite FTS5",
            DiagnosticStatus.FAILURE,
            f"SQLite 未启用 FTS5: {error}",
            "请安装包含 FTS5 扩展的 Python/SQLite 发行版。",
        )
    return DiagnosticResult("SQLite FTS5", DiagnosticStatus.PASS, "内存数据库可创建 FTS5 虚拟表。")


def _check_python_package(name: str, package: str, *, required: bool) -> DiagnosticResult:
    try:
        importlib.import_module(package)
    except Exception as error:
        status = DiagnosticStatus.FAILURE if required else DiagnosticStatus.WARNING
        return DiagnosticResult(
            name,
            status,
            f"无法导入 {package}: {error}",
            "请重新安装项目依赖，例如运行 `uv sync`。",
        )
    return DiagnosticResult(name, DiagnosticStatus.PASS, f"{package} 可导入。")


def _check_git() -> DiagnosticResult:
    executable = shutil.which("git")
    if executable is None:
        return DiagnosticResult(
            "Git",
            DiagnosticStatus.WARNING,
            "未找到 git 可执行文件。",
            "如需使用 `ragdb repo` 导入 GitHub 仓库，请安装 Git 并确保其位于 PATH。",
        )
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return DiagnosticResult(
            "Git",
            DiagnosticStatus.WARNING,
            f"无法执行 git --version: {error}",
            "如需使用 `ragdb repo`，请修复 Git 安装或 PATH。",
        )
    if completed.returncode != 0:
        return DiagnosticResult(
            "Git",
            DiagnosticStatus.WARNING,
            "git --version 返回非零状态。",
            "如需使用 `ragdb repo`，请修复 Git 安装或 PATH。",
        )
    return DiagnosticResult("Git", DiagnosticStatus.PASS, completed.stdout.strip() or "Git 可用。")


def _check_local_embedding_dependency(settings: AppSettings) -> DiagnosticResult:
    result = _check_python_package("本地嵌入依赖", "sentence_transformers", required=settings.embedding.provider == "local")
    if settings.embedding.provider == "cloud" and result.status is DiagnosticStatus.PASS:
        return DiagnosticResult(result.name, result.status, "sentence_transformers 可导入（当前未启用本地嵌入）。")
    return result


def _check_ollama_embedding_configuration(settings: AppSettings) -> DiagnosticResult:
    if settings.embedding.provider != "ollama":
        return DiagnosticResult("Ollama 嵌入配置", DiagnosticStatus.PASS, "当前未启用 Ollama 嵌入。")
    if not settings.embedding.ollama_model.strip() or not settings.embedding.ollama_base_url.strip():
        return DiagnosticResult("Ollama 嵌入配置", DiagnosticStatus.FAILURE, "缺少模型名称或服务地址。", "设置 embedding.ollama_model 与 embedding.ollama_base_url。")
    return DiagnosticResult("Ollama 嵌入配置", DiagnosticStatus.PASS, "本地 Ollama 嵌入配置完整；未发送 API 请求。")


def _check_cloud_embedding_configuration(settings: AppSettings) -> DiagnosticResult:
    if settings.embedding.provider != "cloud":
        return DiagnosticResult("云端嵌入配置", DiagnosticStatus.PASS, "当前未启用云端嵌入。")
    missing: list[str] = []
    if not settings.embedding.cloud_model.strip():
        missing.append("embedding.cloud_model")
    if not settings.embedding.cloud_base_url.strip():
        missing.append("embedding.cloud_base_url")
    api_key = settings.embedding.cloud_api_key
    if api_key is None or not api_key.get_secret_value().strip():
        missing.append("RAGDB_EMBEDDING__CLOUD_API_KEY")
    if missing:
        return DiagnosticResult(
            "云端嵌入配置",
            DiagnosticStatus.FAILURE,
            f"缺少 {', '.join(missing)}。",
            "补齐云端模型、Base URL，并通过 .env 或环境变量设置 API Key。",
        )
    return DiagnosticResult("云端嵌入配置", DiagnosticStatus.PASS, "云端嵌入配置完整；未发送 API 请求。")


def _check_chat_configuration(settings: AppSettings) -> DiagnosticResult:
    if settings.chat.provider == "local":
        if not settings.chat.local_model.strip() or not settings.chat.local_base_url.strip():
            return DiagnosticResult("本地问答配置", DiagnosticStatus.FAILURE, "缺少本地模型或 Base URL。", "设置 chat.local_model 与 chat.local_base_url。")
        return DiagnosticResult("本地问答配置", DiagnosticStatus.PASS, "本地模型配置完整；未发送 API 请求。")
    missing: list[str] = []
    if not settings.chat.cloud_model.strip():
        missing.append("chat.cloud_model")
    if not settings.chat.cloud_base_url.strip():
        missing.append("chat.cloud_base_url")
    if settings.chat.cloud_api_key is None or not settings.chat.cloud_api_key.get_secret_value().strip():
        missing.append("RAGDB_CHAT__CLOUD_API_KEY")
    if missing:
        return DiagnosticResult("云端问答配置", DiagnosticStatus.FAILURE, f"缺少 {', '.join(missing)}。", "通过 .env 或环境变量设置 API Key。")
    return DiagnosticResult("云端问答配置", DiagnosticStatus.PASS, "云端模型配置完整；未发送 API 请求。")


def _check_ocr(settings: AppSettings) -> DiagnosticResult:
    if not settings.ocr.enabled:
        return DiagnosticResult("OCR", DiagnosticStatus.PASS, "当前未启用 OCR。")
    path = settings.ocr.executable_path
    if path is None or not path.is_file():
        return DiagnosticResult("OCR", DiagnosticStatus.FAILURE, "未找到 Tesseract 可执行文件。", "设置 ocr.executable_path 为 tesseract.exe 的完整路径。")
    completed = subprocess.run([str(path), "--list-langs"], capture_output=True, text=True, timeout=5, check=False)
    available = set(completed.stdout.splitlines()[1:])
    missing = set(settings.ocr.languages.split("+")) - available
    if completed.returncode or missing:
        return DiagnosticResult("OCR", DiagnosticStatus.FAILURE, f"缺少语言包：{', '.join(sorted(missing)) or '无法查询'}。", "安装所需 traineddata 文件后重试。")
    return DiagnosticResult("OCR", DiagnosticStatus.PASS, f"Tesseract 可用，语言：{settings.ocr.languages}。")
