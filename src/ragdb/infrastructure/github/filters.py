from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ragdb.application.ingestion import source_type_for_path
from ragdb.domain.errors import WebCrawlError


def normalize_github_url(url: str) -> str:
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.query or parsed.fragment or len(parts) != 2:
        raise WebCrawlError(url, "仅支持公开 GitHub HTTPS 仓库地址")
    owner, repository = parts
    repository = repository.removesuffix(".git")
    if not owner or not repository:
        raise WebCrawlError(url, "仓库地址无效")
    return urlunsplit(("https", "github.com", f"/{owner}/{repository}", "", ""))


def is_importable_file(path: Path, maximum: int) -> bool:
    return path.is_file() and path.stat().st_size <= maximum and source_type_for_path(path) is not None and b"\0" not in path.read_bytes()[:8192]
