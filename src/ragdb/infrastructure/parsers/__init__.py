"""Local document parsers and parser selection."""

from ragdb.infrastructure.parsers.code import CodeParser
from ragdb.infrastructure.parsers.markdown import MarkdownParser
from ragdb.infrastructure.parsers.pdf import PdfParser
from ragdb.infrastructure.parsers.powerpoint import PowerPointParser
from ragdb.infrastructure.parsers.registry import ParserRegistry
from ragdb.infrastructure.parsers.text import TextParser
from ragdb.infrastructure.parsers.word import WordParser

__all__ = [
    "CodeParser",
    "MarkdownParser",
    "ParserRegistry",
    "PdfParser",
    "PowerPointParser",
    "TextParser",
    "WordParser",
]
