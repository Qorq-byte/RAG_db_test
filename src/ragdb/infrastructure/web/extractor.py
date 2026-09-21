"""Extract readable content and links from HTML pages."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

import trafilatura

from ragdb.domain.errors import WebCrawlError


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """The content needed to turn an HTML page into a source."""

    title: str
    text: str
    links: tuple[str, ...]


class _LinkAndTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self._title_parts).split())


def extract_page(html: str, url: str) -> ExtractedPage:
    """Return the main readable text and outgoing HTML links from *html*."""

    parser = _LinkAndTitleParser()
    parser.feed(html)
    text = trafilatura.extract(html, include_links=False, include_tables=True)
    if text is None or not text.strip():
        raise WebCrawlError(url, "未能提取可索引的正文")
    return ExtractedPage(
        title=parser.title or url,
        text=text.strip(),
        links=tuple(parser.links),
    )
