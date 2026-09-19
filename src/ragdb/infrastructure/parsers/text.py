"""Plain-text parser."""

from pathlib import Path

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Document, DocumentUnit, Source, SourcePosition
from ragdb.infrastructure.parsers._common import source_path


def read_text(path: Path, uri: str) -> tuple[str, str]:
    data = path.read_bytes()
    encodings = ("utf-8-sig", "utf-16") if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig",)
    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise DocumentParseError(uri, "文本不是有效的 UTF-8 或带 BOM 的 UTF-16")


class TextParser:
    name = "text"
    version = "1.0"

    def supports(self, source: Source) -> bool:
        return source.source_type is SourceType.TEXT

    def parse(self, source: Source) -> Document:
        path = source_path(source)
        text, encoding = read_text(path, source.uri)
        text = text.strip()
        if not text:
            raise DocumentParseError(source.uri, "文件不包含可解析文本")
        line_count = max(1, len(text.splitlines()))
        return Document(
            source_id=source.id,
            title=source.title,
            units=(
                DocumentUnit(
                    text=text,
                    position=SourcePosition(line_start=1, line_end=line_count),
                    metadata={"encoding": encoding},
                ),
            ),
            metadata={"format": "text", "filename": path.name},
        )
