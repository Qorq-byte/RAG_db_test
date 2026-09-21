from collections import defaultdict

import httpx
import pytest

from ragdb.config import CrawlSettings
from ragdb.domain.errors import WebCrawlError
from ragdb.infrastructure.web.crawler import WebCrawler, normalize_url


def _client(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        response = routes.get(str(request.url))
        if response is None:
            return httpx.Response(404, request=request)
        return response

    return httpx.Client(transport=httpx.MockTransport(handler))


def _response(url: str, html: str, *, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, text=html, headers=headers, request=httpx.Request("GET", url))


def _page(title: str, body: str) -> str:
    return f"<html><head><title>{title}</title></head><body><article><p>{body}。这是用于验证正文提取和安全抓取边界的测试内容。</p></article></body></html>"


def test_normalize_url_removes_fragment_and_default_port() -> None:
    assert normalize_url("HTTPS://Example.COM:443/docs#section") == "https://example.com/docs"


def test_normalize_url_rejects_credentials_and_non_http() -> None:
    with pytest.raises(WebCrawlError):
        normalize_url("https://user:secret@example.com/")
    with pytest.raises(WebCrawlError):
        normalize_url("file:///tmp/page.html")


def test_crawl_honors_robots_same_origin_depth_and_page_limit() -> None:
    routes = {
        "https://example.test/robots.txt": _response("https://example.test/robots.txt", "User-agent: *\nDisallow: /private"),
        "https://example.test/": _response("https://example.test/", _page("Home", "Home body <a href='/one#x'>one</a><a href='/private'>no</a><a href='https://else.test/x'>out</a>"), headers={"content-type": "text/html"}),
        "https://example.test/one": _response("https://example.test/one", _page("One", "One body <a href='/two'>two</a>"), headers={"content-type": "text/html"}),
        "https://example.test/two": _response("https://example.test/two", _page("Two", "Two body"), headers={"content-type": "text/html"}),
    }
    crawler = WebCrawler(CrawlSettings(max_depth=1, max_pages=1, requests_per_second=1000), _client(routes))

    pages = crawler.crawl("https://example.test/#top")

    assert [(page.url, page.depth) for page in pages] == [("https://example.test/", 0)]


def test_crawl_skips_robots_denied_and_cross_origin_redirect() -> None:
    routes = {
        "https://example.test/robots.txt": _response("https://example.test/robots.txt", "User-agent: *\nDisallow: /blocked"),
        "https://example.test/": _response("https://example.test/", _page("Root", "Root text <a href='/blocked'>blocked</a><a href='/jump'>jump</a>"), headers={"content-type": "text/html"}),
        "https://example.test/jump": _response("https://example.test/jump", "", status=302, headers={"location": "https://else.test/"}),
    }
    crawler = WebCrawler(CrawlSettings(max_depth=1, max_pages=5, requests_per_second=1000), _client(routes))

    assert [page.url for page in crawler.crawl("https://example.test/")] == ["https://example.test/"]


def test_robots_fetch_failure_refuses_crawl() -> None:
    crawler = WebCrawler(CrawlSettings(), _client({}))

    with pytest.raises(WebCrawlError, match="robots.txt"):
        crawler.crawl("https://example.test/")


def test_crawl_rate_limits_page_requests() -> None:
    current = [0.0]
    sleeps: list[float] = []
    routes = {
        "https://example.test/robots.txt": _response("https://example.test/robots.txt", "User-agent: *\nAllow: /"),
        "https://example.test/": _response("https://example.test/", _page("Root", "Root <a href='/next'>next</a>"), headers={"content-type": "text/html"}),
        "https://example.test/next": _response("https://example.test/next", _page("Next", "Next"), headers={"content-type": "text/html"}),
    }
    crawler = WebCrawler(
        CrawlSettings(max_depth=1, max_pages=2, requests_per_second=2),
        _client(routes),
        clock=lambda: current[0],
        sleep=lambda delay: sleeps.append(delay),
    )

    crawler.crawl("https://example.test/")

    assert sleeps == [0.5]
