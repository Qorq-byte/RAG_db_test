"""Code chunking that prefers top-level Python symbols and line boundaries."""

import ast
import re
from uuid import UUID

from ragdb.domain.models import Chunk, Document, SourcePosition
from ragdb.infrastructure.chunking._common import Fragment, build_chunks
from ragdb.infrastructure.chunking.text import _validate_sizes


_GENERIC_SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:class|def|function|func|fn|interface|struct)\s+([\w$]+)",
    re.MULTILINE,
)


class CodeChunker:
    name = "structured_code"

    def __init__(self, max_characters: int = 1200, overlap_characters: int = 200) -> None:
        _validate_sizes(max_characters, overlap_characters)
        self.max_characters = max_characters
        self.overlap_characters = overlap_characters

    def chunk(
        self,
        document: Document,
        collection_id: UUID,
        source_content_hash: str,
        generation: int,
    ) -> tuple[Chunk, ...]:
        fragments: list[Fragment] = []
        for unit_index, unit in enumerate(document.units):
            language = str(unit.metadata.get("language", document.metadata.get("language", "")))
            if language == "python":
                extracted = _python_fragments(unit.text, unit.position, dict(unit.metadata), unit_index)
            else:
                extracted = _generic_fragments(unit.text, unit.position, dict(unit.metadata), unit_index)
            fragments.extend(extracted)

        return build_chunks(
            document=document,
            fragments=fragments,
            collection_id=collection_id,
            source_content_hash=source_content_hash,
            generation=generation,
            max_characters=self.max_characters,
            overlap_characters=self.overlap_characters,
            chunker_name=self.name,
        )


def _python_fragments(
    text: str,
    position: SourcePosition,
    metadata: dict,
    unit_index: int,
) -> list[Fragment]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _generic_fragments(text, position, metadata, unit_index)

    lines = text.splitlines()
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if not definitions:
        return [_whole_code_fragment(text, position, metadata, unit_index)]

    fragments: list[Fragment] = []
    cursor = 1
    base_line = position.line_start or 1
    for node in definitions:
        if node.lineno > cursor:
            preamble = "\n".join(lines[cursor - 1 : node.lineno - 1]).strip()
            if preamble:
                fragments.append(
                    _code_fragment(preamble, base_line + cursor - 1, base_line + node.lineno - 2, position, metadata, (unit_index, "preamble", cursor), None)
                )
        end_line = node.end_lineno or node.lineno
        body = "\n".join(lines[node.lineno - 1 : end_line]).strip()
        fragments.append(
            _code_fragment(body, base_line + node.lineno - 1, base_line + end_line - 1, position, metadata, (unit_index, node.name, node.lineno), node.name)
        )
        cursor = end_line + 1
    if cursor <= len(lines):
        tail = "\n".join(lines[cursor - 1 :]).strip()
        if tail:
            fragments.append(
                _code_fragment(tail, base_line + cursor - 1, base_line + len(lines) - 1, position, metadata, (unit_index, "tail", cursor), None)
            )
    return fragments


def _generic_fragments(
    text: str,
    position: SourcePosition,
    metadata: dict,
    unit_index: int,
) -> list[Fragment]:
    matches = list(_GENERIC_SYMBOL.finditer(text))
    if not matches:
        return [_whole_code_fragment(text, position, metadata, unit_index)]
    fragments: list[Fragment] = []
    starts = [match.start() for match in matches] + [len(text)]
    if starts[0] > 0 and text[: starts[0]].strip():
        fragments.append(_whole_code_fragment(text[: starts[0]], position, metadata, unit_index))
    base_line = position.line_start or 1
    for index, match in enumerate(matches):
        body = text[starts[index] : starts[index + 1]].strip()
        start_line = base_line + text.count("\n", 0, starts[index])
        end_line = start_line + max(0, body.count("\n"))
        symbol = match.group(1)
        fragments.append(
            _code_fragment(body, start_line, end_line, position, metadata, (unit_index, symbol, start_line), symbol)
        )
    return fragments


def _whole_code_fragment(text: str, position: SourcePosition, metadata: dict, unit_index: int) -> Fragment:
    return Fragment(text=text, position=position, metadata=metadata, boundary_key=(unit_index, "file"))


def _code_fragment(
    text: str,
    line_start: int,
    line_end: int,
    original: SourcePosition,
    metadata: dict,
    boundary_key: tuple,
    symbol: str | None,
) -> Fragment:
    return Fragment(
        text=text,
        position=SourcePosition(
            page=original.page,
            slide=original.slide,
            line_start=line_start,
            line_end=line_end,
            anchor=original.anchor,
            heading_path=original.heading_path,
            code_symbol=symbol,
        ),
        metadata=metadata,
        boundary_key=boundary_key,
    )
