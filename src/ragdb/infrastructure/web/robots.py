"""Robots exclusion protocol fetching and evaluation."""

from __future__ import annotations

from urllib import robotparser
from urllib.parse import urlsplit

import httpx

from ragdb.domain.errors import WebCrawlError


def robots_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise WebCrawlError(url, "URL 缺少协议或主机名")
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


class RobotsPolicy:
    """Fetch and cache robots policies; failures deny crawling by design."""

    def __init__(self, client: httpx.Client, user_agent: str) -> None:
        self.client = client
        self.user_agent = user_agent
        self._policies: dict[str, robotparser.RobotFileParser] = {}

    def allows(self, url: str) -> bool:
        location = robots_url(url)
        policy = self._policies.get(location)
        if policy is None:
            try:
                response = self.client.get(location, follow_redirects=False)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise WebCrawlError(url, f"无法获取 robots.txt：{exc}") from exc
            policy = robotparser.RobotFileParser()
            policy.set_url(location)
            policy.parse(response.text.splitlines())
            self._policies[location] = policy
        return policy.can_fetch(self.user_agent, url)
