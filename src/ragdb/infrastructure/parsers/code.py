"""Source-code parser with language and line metadata."""

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Document, DocumentUnit, Source, SourcePosition
from ragdb.infrastructure.parsers._common import source_path
from ragdb.infrastructure.parsers.text import read_text


LANGUAGES = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cs": "csharp", ".css": "css",
    ".go": "go", ".h": "c", ".hpp": "cpp", ".html": "html", ".java": "java",
    ".js": "javascript", ".jsx": "javascript", ".kt": "kotlin", ".php": "php",
    ".py": "python", ".rb": "ruby", ".rs": "rust", ".sh": "shell",
    ".sql": "sql", ".swift": "swift", ".ts": "typescript", ".tsx": "typescript",
    ".vue": "vue", ".xml": "xml", ".yaml": "yaml", ".yml": "yaml",
}


class CodeParser:
    name = "code"
    version = "1.0"

    def supports(self, source: Source) -> bool:
        return source.source_type is SourceType.CODE

    def parse(self, source: Source) -> Document:
        path = source_path(source)
        text, encoding = read_text(path, source.uri)
        text = text.rstrip()
        if not text:
            raise DocumentParseError(source.uri, "文件不包含可解析代码")
        language = LANGUAGES.get(path.suffix.lower(), "plain_text")
        line_count = max(1, len(text.splitlines()))
        return Document(
            source_id=source.id,
            title=source.title,
            units=(
                DocumentUnit(
                    text=text,
                    position=SourcePosition(line_start=1, line_end=line_count),
                    metadata={"language": language, "encoding": encoding},
                ),
            ),
            metadata={"format": "code", "filename": path.name, "language": language},
        )
