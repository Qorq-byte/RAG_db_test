"""Markdown parser that preserves heading paths and source line ranges."""

import re

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Document, DocumentUnit, Source, SourcePosition
from ragdb.infrastructure.parsers._common import source_path
from ragdb.infrastructure.parsers.text import read_text


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class MarkdownParser:
    name = "markdown"
    version = "1.0"

    def supports(self, source: Source) -> bool:
        return source.source_type is SourceType.MARKDOWN

    def parse(self, source: Source) -> Document:
        path = source_path(source)
        text, encoding = read_text(path, source.uri)
        lines = text.splitlines()
        units: list[DocumentUnit] = []
        headings: list[str] = []
        section: list[str] = []
        section_start = 1
        section_path: tuple[str, ...] = ()

        def flush(end_line: int) -> None:
            content = "\n".join(section).strip()
            if content:
                units.append(
                    DocumentUnit(
                        text=content,
                        position=SourcePosition(
                            line_start=section_start,
                            line_end=end_line,
                            heading_path=section_path,
                        ),
                        metadata={"format": "markdown"},
                    )
                )

        for line_number, line in enumerate(lines, start=1):
            match = _HEADING.match(line)
            if match:
                flush(line_number - 1)
                level = len(match.group(1))
                heading = match.group(2).strip()
                headings[:] = headings[: level - 1]
                headings.append(heading)
                section = [line]
                section_start = line_number
                section_path = tuple(headings)
            else:
                section.append(line)
        flush(len(lines))

        if not units:
            raise DocumentParseError(source.uri, "文件不包含可解析文本")
        return Document(
            source_id=source.id,
            title=source.title,
            units=tuple(units),
            metadata={"format": "markdown", "filename": path.name, "encoding": encoding},
        )
