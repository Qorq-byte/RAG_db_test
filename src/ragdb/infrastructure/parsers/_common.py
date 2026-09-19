"""Shared, deliberately small helpers for local-file parsers."""

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Source


def source_path(source: Source) -> Path:
    """Resolve a plain path or a local ``file://`` URI without touching the file."""
    if source.uri.lower().startswith("file:"):
        parsed = urlparse(source.uri)
        if parsed.netloc not in ("", "localhost"):
            raise DocumentParseError(source.uri, "仅支持本地 file URI")
        path = Path(url2pathname(unquote(parsed.path)))
    else:
        path = Path(source.uri)

    if not path.is_file():
        raise DocumentParseError(source.uri, "文件不存在或不是普通文件")
    return path


def non_whitespace_count(text: str) -> int:
    return sum(not char.isspace() for char in text)
