"""PDF text-layer parser with low-density OCR detection."""

import pymupdf

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import DocumentParseError, OcrRequiredError
from ragdb.domain.models import Document, DocumentUnit, Source, SourcePosition
from ragdb.infrastructure.parsers._common import non_whitespace_count, source_path


class PdfParser:
    name = "pdf"
    version = "1.0"

    def __init__(self, min_characters_per_page: int = 40) -> None:
        if min_characters_per_page < 1:
            raise ValueError("min_characters_per_page must be positive")
        self.min_characters_per_page = min_characters_per_page

    def supports(self, source: Source) -> bool:
        return source.source_type is SourceType.PDF

    def parse(self, source: Source) -> Document:
        path = source_path(source)
        units: list[DocumentUnit] = []
        low_text_pages: list[int] = []
        try:
            with pymupdf.open(path) as pdf:
                page_count = pdf.page_count
                for page_number, page in enumerate(pdf, start=1):
                    text = page.get_text("text").strip()
                    character_count = non_whitespace_count(text)
                    if character_count < self.min_characters_per_page:
                        low_text_pages.append(page_number)
                    if text:
                        units.append(
                            DocumentUnit(
                                text=text,
                                position=SourcePosition(page=page_number),
                                metadata={"character_count": character_count},
                            )
                        )
        except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
            raise DocumentParseError(source.uri, str(exc)) from exc

        if page_count == 0:
            raise DocumentParseError(source.uri, "PDF 不包含页面")
        if len(low_text_pages) == page_count:
            raise OcrRequiredError(source.uri, tuple(low_text_pages))
        return Document(
            source_id=source.id,
            title=source.title,
            units=tuple(units),
            metadata={
                "format": "pdf",
                "filename": path.name,
                "page_count": page_count,
                "ocr_suggested": bool(low_text_pages),
                "ocr_pages": low_text_pages,
            },
        )
