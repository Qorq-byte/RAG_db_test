"""Word document parser preserving headings and tables."""

import re

from docx import Document as open_docx
from docx.table import Table

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import DocumentParseError
from ragdb.domain.models import Document, DocumentUnit, Source, SourcePosition
from ragdb.infrastructure.parsers._common import source_path


_HEADING_STYLE = re.compile(r"Heading\s+(\d+)", re.IGNORECASE)


class WordParser:
    name = "word"
    version = "1.0"

    def supports(self, source: Source) -> bool:
        return source.source_type is SourceType.WORD

    def parse(self, source: Source) -> Document:
        path = source_path(source)
        try:
            document = open_docx(path)
        except Exception as exc:
            raise DocumentParseError(source.uri, str(exc)) from exc

        units: list[DocumentUnit] = []
        headings: list[str] = []
        paragraph_index = 0
        table_index = 0
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                table_index += 1
                rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in block.rows]
                text = "\n".join(row for row in rows if row.strip(" |"))
                if text:
                    units.append(
                        DocumentUnit(
                            text=text,
                            position=SourcePosition(heading_path=tuple(headings)),
                            metadata={"block_type": "table", "table_index": table_index},
                        )
                    )
                continue

            paragraph_index += 1
            text = block.text.strip()
            if not text:
                continue
            style = block.style.name if block.style is not None else ""
            heading_match = _HEADING_STYLE.fullmatch(style)
            if heading_match:
                level = int(heading_match.group(1))
                headings[:] = headings[: level - 1]
                headings.append(text)
            units.append(
                DocumentUnit(
                    text=text,
                    position=SourcePosition(heading_path=tuple(headings)),
                    metadata={
                        "block_type": "paragraph",
                        "paragraph_index": paragraph_index,
                        "style": style,
                    },
                )
            )

        if not units:
            raise DocumentParseError(source.uri, "文档不包含可解析文本")
        native_title = (document.core_properties.title or "").strip()
        metadata: dict[str, str | int] = {"format": "docx", "filename": path.name}
        if native_title:
            metadata["native_title"] = native_title
        return Document(source_id=source.id, title=source.title, units=tuple(units), metadata=metadata)
