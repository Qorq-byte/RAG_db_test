from pathlib import Path

import pytest

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import DocumentParseError
from ragdb.infrastructure.parsers.code import CodeParser
from ragdb.infrastructure.parsers.markdown import MarkdownParser
from ragdb.infrastructure.parsers.text import TextParser


SAMPLES = Path(__file__).parents[2] / "samples"


def test_text_parser_preserves_line_range(make_source) -> None:
    document = TextParser().parse(make_source(SAMPLES / "sample.txt", SourceType.TEXT))
    assert document.units[0].position.line_start == 1
    assert document.units[0].position.line_end == 2
    assert document.metadata["filename"] == "sample.txt"


def test_markdown_parser_preserves_heading_hierarchy(make_source) -> None:
    document = MarkdownParser().parse(make_source(SAMPLES / "sample.md", SourceType.MARKDOWN))
    assert len(document.units) == 2
    assert document.units[0].position.heading_path == ("RAG 笔记",)
    assert document.units[1].position.heading_path == ("RAG 笔记", "检索")
    assert document.units[1].position.line_start == 5


def test_code_parser_detects_language_and_lines(make_source) -> None:
    document = CodeParser().parse(make_source(SAMPLES / "sample.py", SourceType.CODE))
    assert document.metadata["language"] == "python"
    assert document.units[0].metadata["language"] == "python"
    assert document.units[0].position.line_end == 3


def test_text_parser_rejects_invalid_encoding(tmp_path, make_source) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\x80\x81")
    with pytest.raises(DocumentParseError, match="UTF-8"):
        TextParser().parse(make_source(path, SourceType.TEXT))
