"""Parser registry and default local parser composition."""

from collections.abc import Iterable

from ragdb.domain.errors import UnsupportedSourceError
from ragdb.domain.models import Document, Source
from ragdb.domain.ports import DocumentParser
from ragdb.infrastructure.parsers.code import CodeParser
from ragdb.infrastructure.parsers.markdown import MarkdownParser
from ragdb.infrastructure.parsers.pdf import PdfParser
from ragdb.infrastructure.parsers.powerpoint import PowerPointParser
from ragdb.infrastructure.parsers.text import TextParser
from ragdb.infrastructure.parsers.word import WordParser


class ParserRegistry:
    def __init__(self, parsers: Iterable[DocumentParser] | None = None) -> None:
        configured = tuple(parsers) if parsers is not None else (
            TextParser(),
            MarkdownParser(),
            PdfParser(),
            WordParser(),
            PowerPointParser(),
            CodeParser(),
        )
        names = [parser.name for parser in configured]
        if len(names) != len(set(names)):
            raise ValueError("parser names must be unique")
        self._parsers = configured

    @property
    def parsers(self) -> tuple[DocumentParser, ...]:
        return self._parsers

    def get_parser(self, source: Source) -> DocumentParser:
        for parser in self._parsers:
            if parser.supports(source):
                return parser
        raise UnsupportedSourceError(source.source_type.value, source.uri)

    def parse(self, source: Source) -> Document:
        return self.get_parser(source).parse(source)
