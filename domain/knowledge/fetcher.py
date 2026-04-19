"""Content fetching from various sources (Threads, Twitter/X, web)."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchedContent:
    """Raw content fetched from a URL."""
    url: str
    source_type: str
    title: str
    text: str
    author: str
    images: list[str]


class _TextExtractor(HTMLParser):
    """Simple HTML to text converter."""

    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._skip = False
        self._skip_tags = {"script", "style", "nav", "footer", "header"}
        self._title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._skip_tags:
            self._skip = True
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li"):
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags:
            self._skip = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title = data.strip()
        if not self._skip:
            self._text.append(data)

    def get_text(self) -> str:
        raw = "".join(self._text)
        lines = [line.strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)

    def get_title(self) -> str:
        return self._title


def _detect_source(url: str) -> str:
    """Auto-detect source type from URL."""
    host = urlparse(url).hostname or ""
    if "threads.net" in host:
        return "threads"
    if "twitter.com" in host or "x.com" in host:
        return "twitter"
    return "web"


def _fetch_web(url: str) -> FetchedContent:
    """Fetch generic web page and extract text content."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            # Try UTF-8 first, then detect from headers
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct)
            if m:
                charset = m.group(1)
            html = raw.decode(charset, errors="replace")
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return FetchedContent(url=url, source_type="web", title="",
                              text=f"[Fetch failed: {exc}]", author="", images=[])

    parser = _TextExtractor()
    parser.feed(html)
    text = parser.get_text()
    title = parser.get_title()

    # Extract image URLs from og:image
    images = []
    og_match = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    if og_match:
        images.append(og_match.group(1))

    # Extract author from meta tags
    author = ""
    author_match = re.search(r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html)
    if author_match:
        author = author_match.group(1)

    return FetchedContent(
        url=url,
        source_type="web",
        title=title[:200],
        text=text[:5000],
        author=author,
        images=images,
    )


def _fetch_threads(url: str) -> FetchedContent:
    """Fetch Threads post. Try Threads API if configured, fallback to web scrape."""
    # For now, use web fetch as baseline. Threads API requires OAuth setup.
    content = _fetch_web(url)
    return FetchedContent(
        url=content.url,
        source_type="threads",
        title=content.title,
        text=content.text,
        author=content.author,
        images=content.images,
    )


def _fetch_twitter(url: str) -> FetchedContent:
    """Fetch Twitter/X post via nitter or web scrape."""
    # Try replacing x.com/twitter.com with a nitter instance for easier parsing
    nitter_url = url
    parsed = urlparse(url)
    if parsed.hostname in ("twitter.com", "x.com"):
        nitter_url = f"https://nitter.privacydev.net{parsed.path}"

    content = _fetch_web(nitter_url)
    if "[Fetch failed" in content.text:
        # Fallback to original URL
        content = _fetch_web(url)

    return FetchedContent(
        url=url,
        source_type="twitter",
        title=content.title,
        text=content.text,
        author=content.author,
        images=content.images,
    )


def fetch_content(url: str, source_type: str = "auto") -> FetchedContent:
    """Fetch content from a URL. Auto-detects source type if not specified."""
    if source_type == "auto":
        source_type = _detect_source(url)

    if source_type == "threads":
        return _fetch_threads(url)
    elif source_type == "twitter":
        return _fetch_twitter(url)
    else:
        return _fetch_web(url)
