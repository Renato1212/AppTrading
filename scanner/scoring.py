"""Compute the real-time trending / attention score for each news event.

The score answers: *how much market-moving attention is this story getting,
right now — and is the market actually reacting?* It blends measurable signals:

  1. Breadth      - how many distinct outlets carry it (tier-weighted).
  2. News velocity - how fast new outlets pick it up.
  3. Social        - REAL real-time attention: StockTwits message velocity +
                     Reddit mention velocity + Google Trends interest on the
                     event's instruments (replaces any fake "views" proxy).
  4. Impact        - market-moving keyword weight (Fed/CPI/OPEC/war/crash...).
  5. Recency       - exponential decay so old stories fade.

and then applies the conviction multiplier that gives the real edge:

  * Market confirmation - when the related futures contract shows an actual
    price move on a volume spike, the score is boosted; a story the market is
    ignoring is dampened.

Final score is squashed to 0-100.
"""

from __future__ import annotations

import math
import time

from .market import InstrumentSignal, MarketContext
from .models import Event
from .sources import INSTRUMENTS, MARKET_IMPACT_TERMS

# --- base weights (news + social attention + impact) ---
W_BREADTH = 0.28
W_VELOCITY = 0.22
W_SOCIAL = 0.28
W_IMPACT = 0.22

# how strongly an actual market reaction multiplies the score
CONFIRMATION_BOOST = 0.7

RECENCY_HALF_LIFE_MIN = 90.0
VELOCITY_WINDOW_MIN = 20.0
TIER_WEIGHT = {1: 1.6, 2: 1.0, 3: 0.6}


def _tier_weighted_breadth(event: Event) -> float:
    by_outlet_best_tier: dict[str, int] = {}
    for art in event.articles:
        cur = by_outlet_best_tier.get(art.outlet)
        if cur is None or art.tier < cur:
            by_outlet_best_tier[art.outlet] = art.tier
    return sum(TIER_WEIGHT.get(t, 1.0) for t in by_outlet_best_tier.values())


def _news_velocity(event: Event, now: float) -> float:
    if len(event.outlet_history) < 2:
        return 0.0
    window_start = now - VELOCITY_WINDOW_MIN * 60.0
    past_count = event.outlet_history[0][1]
    for ts, count in event.outlet_history:
        if ts <= window_start:
            past_count = count
        else:
            break
    gained = max(0, event.outlet_history[-1][1] - past_count)
    return gained / VELOCITY_WINDOW_MIN


def _market_impact(event: Event) -> float:
    text = " ".join(a.text.lower() for a in event.articles)
    score = 0.0
    for term, weight in MARKET_IMPACT_TERMS.items():
        if term in text:
            score = max(score, weight)
            score += weight * 0.15
    return min(score, 1.5)


def _recency(event: Event, now: float) -> float:
    age_min = (now - event.last_update_ts) / 60.0
    return 0.5 ** (age_min / RECENCY_HALF_LIFE_MIN)


def _instruments(event: Event) -> list[str]:
    text = " ".join(a.text.lower() for a in event.articles)
    hits: list[tuple[str, int]] = []
    for symbol, meta in INSTRUMENTS.items():
        n = sum(1 for kw in meta["keywords"] if kw in text)
        if n:
            hits.append((symbol, n))
    hits.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in hits]


def _social_score(sig: InstrumentSignal) -> float:
    """Real-time attention for one instrument, 0..~1.3."""
    s = (
        0.5 * math.tanh(sig.social_velocity / 2.0)
        + 0.3 * math.tanh(sig.reddit_velocity / 0.3)
        + 0.2 * (sig.trends_interest / 100.0)
    )
    if sig.is_trending:
        s += 0.3
    return s


def _confirmation_score(sig: InstrumentSignal) -> float:
    """Market reaction for one instrument, 0..1."""
    if not sig.price_ok:
        return 0.0
    move = math.tanh(abs(sig.price_pct) / 0.8)
    vol = math.tanh(max(0.0, sig.volume_spike - 1.0) / 1.0)
    return 0.6 * move + 0.4 * vol


def _aggregate(event: Event, context: MarketContext) -> tuple[float, float, dict]:
    """Aggregate social + confirmation over the event's instruments (max-driven)."""
    best_social = 0.0
    best_conf = 0.0
    detail: dict = {}
    for sym in event.instruments:
        sig = context.signal(sym)
        if not sig:
            continue
        soc = _social_score(sig)
        conf = _confirmation_score(sig)
        best_social = max(best_social, soc)
        best_conf = max(best_conf, conf)
        if soc > 0 or conf > 0 or sig.price_ok:
            detail[sym] = {
                "social": round(soc, 3),
                "confirmation": round(conf, 3),
                "price_pct": sig.price_pct,
                "volume_spike": sig.volume_spike,
                "social_velocity": sig.social_velocity,
                "reddit_velocity": sig.reddit_velocity,
                "trends": sig.trends_interest,
                "sentiment": sig.sentiment,
                "trending": sig.is_trending,
            }
    return min(best_social, 1.0), min(best_conf, 1.0), detail


def score_event(event: Event, context: MarketContext, now: float | None = None) -> None:
    now = now or time.time()

    event.instruments = _instruments(event)
    impact = _market_impact(event)

    breadth_n = math.tanh(_tier_weighted_breadth(event) / 6.0)
    velocity_n = math.tanh(_news_velocity(event, now) / 0.5)
    impact_n = min(impact, 1.0)
    recency = _recency(event, now)
    social_n, confirmation_n, market_detail = _aggregate(event, context)

    base = (
        W_BREADTH * breadth_n
        + W_VELOCITY * velocity_n
        + W_SOCIAL * social_n
        + W_IMPACT * impact_n
    )
    # market confirmation is the conviction multiplier (the real edge);
    # impact gives a smaller secondary multiplier.
    multiplier = (1.0 + CONFIRMATION_BOOST * confirmation_n) * (1.0 + 0.4 * impact_n)
    score = 100.0 * base * recency * multiplier

    event.market_impact = round(impact, 3)
    event.score = round(min(score, 100.0), 2)
    event.score_breakdown = {
        "breadth": round(breadth_n, 3),
        "news_velocity": round(velocity_n, 3),
        "social": round(social_n, 3),
        "impact": round(impact_n, 3),
        "confirmation": round(confirmation_n, 3),
        "recency": round(recency, 3),
        "outlets": event.outlet_count,
        "articles": event.article_count,
        "top_tier": event.max_tier_rank,
        "market": market_detail,
    }


def score_all(events: list[Event], context: MarketContext | None = None, now: float | None = None) -> list[Event]:
    now = now or time.time()
    context = context or MarketContext()
    for ev in events:
        score_event(ev, context, now)
    return sorted(events, key=lambda e: e.score, reverse=True)
