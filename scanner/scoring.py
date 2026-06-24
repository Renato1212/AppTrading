"""Compute the real-time trending / attention score for each news event.

The score answers: *how much market-moving attention is this story getting,
right now?* It blends five measurable signals:

  1. Breadth   - how many distinct outlets are publishing it (tier-weighted).
  2. Velocity  - how fast new outlets are picking it up (acceleration of breadth).
  3. Attention - a views/engagement proxy where feeds expose it, else breadth.
  4. Impact    - market-moving keyword weight (Fed/CPI/OPEC/war/crash ...).
  5. Recency   - exponential decay so old stories fade from the top.

Final score is squashed to a 0-100 scale for an at-a-glance trending board.
"""

from __future__ import annotations

import math
import time

from .models import Event
from .sources import INSTRUMENTS, MARKET_IMPACT_TERMS

# --- tunable weights -----------------------------------------------------
W_BREADTH = 0.34
W_VELOCITY = 0.26
W_ATTENTION = 0.16
W_IMPACT = 0.24

RECENCY_HALF_LIFE_MIN = 90.0     # a story loses half its score every 90 min
VELOCITY_WINDOW_MIN = 20.0       # window for measuring outlet pickup rate
TIER_WEIGHT = {1: 1.6, 2: 1.0, 3: 0.6}   # a wire pickup counts more than an aggregator


def _tier_weighted_breadth(event: Event) -> float:
    """Distinct outlets, weighted so wires count more than aggregators."""
    by_outlet_best_tier: dict[str, int] = {}
    for art in event.articles:
        cur = by_outlet_best_tier.get(art.outlet)
        if cur is None or art.tier < cur:
            by_outlet_best_tier[art.outlet] = art.tier
    return sum(TIER_WEIGHT.get(t, 1.0) for t in by_outlet_best_tier.values())


def _velocity(event: Event, now: float) -> float:
    """Outlet pickup rate over the recent window (new outlets per minute).

    Uses the recorded outlet-count history. A story that jumped from 1 to 6
    outlets in the last 20 minutes is accelerating and scores high here.
    """
    if len(event.outlet_history) < 2:
        return 0.0
    window_start = now - VELOCITY_WINDOW_MIN * 60.0
    past_count = event.outlet_history[0][1]
    for ts, count in event.outlet_history:
        if ts <= window_start:
            past_count = count
        else:
            break
    current_count = event.outlet_history[-1][1]
    gained = max(0, current_count - past_count)
    return gained / VELOCITY_WINDOW_MIN  # outlets per minute


def _attention_proxy(event: Event) -> float:
    """Engagement proxy: real views if present, else breadth+volume stand-in."""
    if event.total_views > 0:
        return math.log10(1 + event.total_views)
    # No view data: approximate attention from coverage volume. More outlets and
    # more repeat-articles imply more eyeballs on the story.
    return math.log2(1 + event.article_count + event.outlet_count)


def _market_impact(event: Event) -> float:
    """Weight by presence of high-impact market-moving terms (0..~1.0)."""
    text = " ".join(a.text.lower() for a in event.articles)
    score = 0.0
    for term, weight in MARKET_IMPACT_TERMS.items():
        if term in text:
            score = max(score, weight)          # strongest single signal
            score += weight * 0.15               # plus a small stacking bonus
    return min(score, 1.5)


def _recency(event: Event, now: float) -> float:
    age_min = (now - event.last_update_ts) / 60.0
    return 0.5 ** (age_min / RECENCY_HALF_LIFE_MIN)


def _instruments(event: Event) -> list[str]:
    """Tag the futures contracts the story is relevant to."""
    text = " ".join(a.text.lower() for a in event.articles)
    hits: list[tuple[str, int]] = []
    for symbol, meta in INSTRUMENTS.items():
        n = sum(1 for kw in meta["keywords"] if kw in text)
        if n:
            hits.append((symbol, n))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in hits]


def score_event(event: Event, now: float | None = None) -> None:
    """Compute and attach the trending score (0-100) and its breakdown."""
    now = now or time.time()

    breadth_raw = _tier_weighted_breadth(event)
    velocity_raw = _velocity(event, now)
    attention_raw = _attention_proxy(event)
    impact = _market_impact(event)
    recency = _recency(event, now)

    # Normalise each signal to roughly 0..1 with diminishing returns so a
    # mega-story doesn't drown everything else.
    breadth_n = math.tanh(breadth_raw / 6.0)
    velocity_n = math.tanh(velocity_raw / 0.5)          # 0.5 new outlets/min -> strong
    attention_n = math.tanh(attention_raw / 4.0)
    impact_n = min(impact, 1.0)

    base = (
        W_BREADTH * breadth_n
        + W_VELOCITY * velocity_n
        + W_ATTENTION * attention_n
        + W_IMPACT * impact_n
    )
    # market impact also acts as a mild multiplier: a story about the Fed with
    # broad coverage should clearly outrank an equally-covered fluff piece.
    multiplier = 1.0 + 0.5 * impact_n
    score = 100.0 * base * multiplier * recency

    event.instruments = _instruments(event)
    event.market_impact = round(impact, 3)
    event.score = round(min(score, 100.0), 2)
    event.score_breakdown = {
        "breadth": round(breadth_n, 3),
        "velocity": round(velocity_n, 3),
        "attention": round(attention_n, 3),
        "impact": round(impact_n, 3),
        "recency": round(recency, 3),
        "outlets": event.outlet_count,
        "articles": event.article_count,
        "outlets_per_min": round(velocity_raw, 3),
        "views": event.total_views or None,
        "top_tier": event.max_tier_rank,
    }


def score_all(events: list[Event], now: float | None = None) -> list[Event]:
    now = now or time.time()
    for ev in events:
        score_event(ev, now)
    return sorted(events, key=lambda e: e.score, reverse=True)
