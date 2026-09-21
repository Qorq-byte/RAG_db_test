"""Same-origin, breadth-first, bounded HTML crawler."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from ragdb.config import CrawlSettings
from ragdb.domain.errors import WebCrawlError
from ragdb.infrastructure.web.extractor import extract_page
from ragdb.infrastructure.web.robots import RobotsPolicy


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    title: str
    text: str
    depth: int


def normalize_url(url: str) -> str:
    """Normalize an HTTP(S) URL without changing its query semantics."""

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise WebCrawlError(url, "仅支持不含凭据的 HTTP(S) URL")
    hostname = parsed.hostname.lower()
    port = parsed.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def same_origin(left: str, right: str) -> bool:
    first = urlsplit(left)
    second = urlsplit(right)
    return (first.scheme, first.hostname, first.port) == (second.scheme, second.hostname, second.port)


class WebCrawler:
    """Crawl HTML pages while enforcing robots and configured resource limits."""

    def __init__(
        self,
        settings: CrawlSettings,
        client: httpx.Client | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            headers={"User-Agent": settings.user_agent}, timeout=settings.timeout_seconds
        )
        self.robots = RobotsPolicy(self.client, settings.user_agent)
        self.clock = clock
        self.sleep = sleep
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def crawl(self, start_url: str) -> tuple[CrawledPage, ...]:
        start = normalize_url(start_url)
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        queued = {start}
        visited: set[str] = set()
        pages: list[CrawledPage] = []
        while queue and len(pages) < self.settings.max_pages:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            if not self.robots.allows(url):
                continue
            response = self._request(url)
            final_url = self._resolve_response_url(start, url, response)
            if final_url is None:
                continue
            if response.is_redirect:
                if final_url not in visited and final_url not in queued:
                    queue.appendleft((final_url, depth))
                    queued.add(final_url)
                continue
            if final_url != url and final_url in visited:
                continue
            if "text/html" not in response.headers.get("content-type", "").lower():
                continue
            extracted = extract_page(response.text, final_url)
            pages.append(CrawledPage(final_url, extracted.title, extracted.text, depth))
            if depth == self.settings.max_depth:
                continue
            for href in extracted.links:
                candidate = self._linked_url(final_url, href)
                if candidate and candidate not in queued and candidate not in visited:
                    queue.append((candidate, depth + 1))
                    queued.add(candidate)
        return tuple(pages)

    def _request(self, url: str) -> httpx.Response:
        interval = 1 / self.settings.requests_per_second
        if self._last_request_at is not None:
            wait = interval - (self.clock() - self._last_request_at)
            if wait > 0:
                self.sleep(wait)
        try:
            response = self.client.get(url, follow_redirects=False)
            if not response.is_redirect:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WebCrawlError(url, f"请求失败：{exc}") from exc
        self._last_request_at = self.clock()
        return response

    def _resolve_response_url(self, start: str, requested: str, response: httpx.Response) -> str | None:
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise WebCrawlError(requested, "重定向缺少目标地址")
            target = normalize_url(urljoin(requested, location))
            if not same_origin(start, target):
                return None
            return target
        if not same_origin(start, requested):
            return None
        return requested

    def _linked_url(self, base: str, href: str) -> str | None:
        try:
            candidate = normalize_url(urljoin(base, href))
        except WebCrawlError:
            return None
        return candidate if same_origin(base, candidate) else None
