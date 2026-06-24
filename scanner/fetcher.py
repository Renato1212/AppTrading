"""Async fetching and parsing of news RSS/Atom feeds."""

from __future__ import annotations

import asyncio
import calendar
import time
from email.utils import parsedate_tz

import httpx

from . import feedparse
from .models import Article
from .sources import SOURCES, Source

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FuturesNewsScanner/1.0; +https://github.com/renato1212/apptrading)"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
}


def _parse_published(raw: str | None) -> float:
    """Best-effort parse of an RSS/Atom date string to unix seconds (UTC)."""
    if not raw:
        return time.time()
    # RFC 822 (RSS pubDate), e.g. "Tue, 24 Jun 2026 14:05:00 GMT"
    parsed = parsedate_tz(raw)
    if parsed:
        offset = parsed[9] or 0
        return calendar.timegm(parsed[:9]) - offset
    # ISO 8601 (Atom), e.g. "2026-06-24T14:05:00Z"
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return calendar.timegm(time.strptime(raw.replace("Z", "+0000") if fmt.endswith("%z") else raw, fmt))
        except ValueError:
            continue
    return time.time()


async def _fetch_one(client: httpx.AsyncClient, source: Source) -> list[Article]:
    now = time.time()
    try:
        resp = await client.get(source.url, headers=_HEADERS, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - one bad feed shouldn't kill the scan
        print(f"[fetch] {source.outlet} / {source.name}: {type(exc).__name__}: {exc}")
        return []

    entries = feedparse.parse(resp.content)
    articles: list[Article] = []
    for entry in entries:
        articles.append(
            Article(
                title=entry.title,
                summary=entry.summary,
                link=entry.link,
                outlet=source.outlet,
                feed_name=source.name,
                tier=source.tier,
                published_ts=_parse_published(entry.published),
                fetched_ts=now,
                views=entry.views,
            )
        )
    return articles


async def fetch_all(sources: list[Source] | None = None) -> list[Article]:
    """Fetch every source concurrently and return a flat list of articles."""
    sources = sources or SOURCES
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_fetch_one(client, s) for s in sources))
    articles = [a for batch in results for a in batch]
    print(f"[fetch] pulled {len(articles)} articles from {len(sources)} feeds")
    return articles
