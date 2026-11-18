"""World news from free RSS feeds (no API key required)."""

from __future__ import annotations

import logging
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import feedparser

import config as cfg

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL = 600
_UA = {"User-Agent": "Mozilla/5.0 (JARVIS news reader)"}


def _download(url: str, timeout: int = 6) -> Optional[bytes]:
    try:
        request = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(2_000_000)
    except Exception as exc:
        log.debug("feed download failed %s: %s", url, exc)
        return None

CATEGORY_QUERIES = {
    "world": "world news",
    "india": "India",
    "technology": "technology",
    "business": "business markets",
    "science": "science",
    "sports": "sports",
    "health": "health",
    "ai": "artificial intelligence",
    "crypto": "crypto markets",
    "local": "Vijayawada",
}


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _feeds(category: str | None) -> list[str]:
    if category and category.lower() not in {"world", "top", "general", "all"}:
        query = CATEGORY_QUERIES.get(category.lower(), category)
        return [f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"]
    return [url.strip() for url in cfg.NEWS_FEEDS.split(",") if url.strip()]


def fetch(category: str | None = None, limit: int = 8) -> list[dict]:
    key = (category or "world").lower()
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1][:limit]

    articles: list[dict] = []
    seen: set[str] = set()
    feeds = _feeds(category)

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(feeds)))) as pool:
        payloads = list(pool.map(_download, feeds))

    for payload in payloads:
        if not payload:
            continue
        try:
            parsed = feedparser.parse(payload)
            for entry in parsed.entries[:15]:
                title = _clean(entry.get("title", ""))
                if not title:
                    continue
                signature = title.lower()[:80]
                if signature in seen:
                    continue
                seen.add(signature)
                source = ""
                if " - " in title:
                    title, source = title.rsplit(" - ", 1)
                if not source:
                    source = _clean(entry.get("source", {}).get("title", "")) or "news"
                articles.append({
                    "title": title.strip(),
                    "source": source.strip(),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": _clean(entry.get("summary", ""))[:300],
                })
        except Exception as exc:
            log.debug("feed parse failed: %s", exc)

    # newest first when timestamps are available, otherwise keep feed order
    def _stamp(item: dict) -> float:
        try:
            return feedparser_datetime(item["published"])
        except Exception:
            return 0.0

    articles.sort(key=_stamp, reverse=True)
    _CACHE[key] = (now, articles)
    return articles[:limit]


def feedparser_datetime(value: str) -> float:
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        return 0.0


def get_news(category: str | None = None, count: int = 5) -> str:
    articles = fetch(category, limit=count)
    if not articles:
        return "I could not reach the news feeds, Sir."
    label = category or "world"
    lines = [f"{a['title']} ({a['source']})" for a in articles[:count]]
    return f"Top {label} headlines: " + ". ".join(lines) + "."


def briefing(category: str | None = None, count: int = 6) -> str:
    """Longer block used for spoken briefings and the HUD ticker."""
    articles = fetch(category, limit=count)
    if not articles:
        return "I could not reach the news feeds, Sir."
    stamp = datetime.now().strftime("%H:%M")
    lines = [f"News briefing at {stamp}."]
    for index, article in enumerate(articles, start=1):
        lines.append(f"{index}. {article['title']}, from {article['source']}.")
    return " ".join(lines)


def headlines(category: str | None = None, count: int = 10) -> list[dict]:
    return fetch(category, limit=count)
