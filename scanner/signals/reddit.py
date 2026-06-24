"""Reddit real-time retail-attention signal.

The velocity of new posts (and their comment/score momentum) on the big retail
trading subs is a real-time gauge of where retail attention is rushing. We pull
the newest posts from r/wallstreetbets, r/stocks and r/investing and count
mentions of each instrument's cashtags/terms in the recent window.

Uses Reddit's public .json endpoints — no OAuth needed at this volume, just a
descriptive User-Agent (Reddit blocks generic/no UA).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

_SUBREDDITS = ["wallstreetbets", "stocks", "investing"]
_HEADERS = {"User-Agent": "python:futures-news-scanner:2.0 (by /u/scanner)"}
_RECENT_WINDOW_MIN = 90.0


@dataclass
class RedditPost:
    title: str
    created_ts: float
    score: int
    num_comments: int
    subreddit: str


@dataclass
class RedditSnapshot:
    posts: list[RedditPost] = field(default_factory=list)

    def mentions(self, terms: list[str]) -> tuple[int, float, int]:
        """Count recent posts mentioning any term.

        Returns (mention_count, velocity_per_min, engagement) where engagement is
        the summed score+comments of the matching posts (momentum behind them).
        """
        now = time.time()
        cutoff = now - _RECENT_WINDOW_MIN * 60
        upper_terms = [t.upper() for t in terms]
        count = 0
        engagement = 0
        for p in self.posts:
            if p.created_ts < cutoff:
                continue
            title_u = p.title.upper()
            if any(t in title_u for t in upper_terms):
                count += 1
                engagement += p.score + p.num_comments
        return count, round(count / _RECENT_WINDOW_MIN, 3), engagement


async def _fetch_sub(client: httpx.AsyncClient, sub: str) -> list[RedditPost]:
    url = f"https://www.reddit.com/r/{sub}/new.json?limit=100"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=10.0)
        if resp.status_code != 200:
            return []
        children = resp.json().get("data", {}).get("children", [])
    except Exception:  # noqa: BLE001
        return []
    posts = []
    for c in children:
        d = c.get("data", {})
        posts.append(
            RedditPost(
                title=d.get("title", ""),
                created_ts=float(d.get("created_utc", 0) or 0),
                score=int(d.get("score", 0) or 0),
                num_comments=int(d.get("num_comments", 0) or 0),
                subreddit=sub,
            )
        )
    return posts


async def fetch_reddit() -> RedditSnapshot:
    async with httpx.AsyncClient() as client:
        batches = await asyncio.gather(*[_fetch_sub(client, s) for s in _SUBREDDITS])
    return RedditSnapshot(posts=[p for b in batches for p in b])
