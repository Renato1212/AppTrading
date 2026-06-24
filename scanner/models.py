"""Core data models for the news scanner."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field


@dataclass
class Article:
    """A single article pulled from one outlet's feed."""

    title: str
    summary: str
    link: str
    outlet: str
    feed_name: str
    tier: int
    published_ts: float          # unix seconds when the outlet published it
    fetched_ts: float            # unix seconds when we first saw it
    views: int | None = None     # engagement proxy if the feed exposes it

    @property
    def uid(self) -> str:
        """Stable id for de-duplicating the same article across refreshes."""
        return hashlib.sha1(self.link.encode("utf-8")).hexdigest()[:16]

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}".strip()


@dataclass
class Event:
    """A cluster of articles from one or more outlets about the same story."""

    event_id: str
    headline: str                       # representative headline (highest tier / earliest)
    articles: list[Article] = field(default_factory=list)
    first_seen_ts: float = 0.0
    last_update_ts: float = 0.0

    # outlet-count history as (timestamp, distinct_outlet_count) so we can
    # compute how fast a story is spreading across publishers (velocity).
    outlet_history: list[tuple[float, int]] = field(default_factory=list)

    # computed each scoring pass
    instruments: list[str] = field(default_factory=list)
    market_impact: float = 0.0
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)

    @property
    def outlets(self) -> set[str]:
        return {a.outlet for a in self.articles}

    @property
    def outlet_count(self) -> int:
        return len(self.outlets)

    @property
    def article_count(self) -> int:
        return len(self.articles)

    @property
    def total_views(self) -> int:
        return sum(a.views or 0 for a in self.articles)

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.first_seen_ts) / 60.0

    @property
    def max_tier_rank(self) -> int:
        """Best (lowest-number) tier covering the story; 1 = wire."""
        return min((a.tier for a in self.articles), default=3)
