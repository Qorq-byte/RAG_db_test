from pathlib import Path

import pytest

from ragdb.domain.enums import SourceType
from ragdb.domain.errors import UnsupportedSourceError
from ragdb.infrastructure.parsers.markdown import MarkdownParser
from ragdb.infrastructure.parsers.registry import ParserRegistry


SAMPLES = Path(__file__).parents[2] / "samples"


def test_default_registry_selects_parser(make_source) -> None:
    source = make_source(SAMPLES / "sample.md", SourceType.MARKDOWN)
    parser = ParserRegistry().get_parser(source)
    assert isinstance(parser, MarkdownParser)


def test_registry_rejects_unsupported_source(make_source) -> None:
    source = make_source(SAMPLES / "sample.txt", SourceType.WEB)
    with pytest.raises(UnsupportedSourceError, match="web"):
        ParserRegistry().get_parser(source)


def test_registry_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="unique"):
        ParserRegistry([MarkdownParser(), MarkdownParser()])
