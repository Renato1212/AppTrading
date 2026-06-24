"""Builds a per-instrument 'market context' from the real-time signals.

Each scan fetches the live attention (StockTwits, Reddit, Google Trends) and
price-reaction (Yahoo) signals once, concurrently, and folds them into one
record per futures contract. The scorer then looks up an event's instruments to
turn raw news coverage into a real, market-aware trending score.

Every signal is best-effort; a missing source just leaves its fields at neutral
defaults. The whole context serialises to/from a dict so it can live in the KV
store between stateless serverless invocations.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field

from .signals.prices import fetch_prices
from .signals.reddit import fetch_reddit
from .signals.stocktwits import fetch_stocktwits
from .signals.trends import fetch_trends
from .sources import INSTRUMENT_MARKETS


@dataclass
class InstrumentSignal:
    symbol: str
    # attention
    social_velocity: float = 0.0      # StockTwits messages/min (recent window)
    social_watchers: int = 0
    sentiment: float = 0.0            # -1..+1
    reddit_velocity: float = 0.0      # matching posts/min (recent window)
    reddit_engagement: int = 0
    trends_interest: float = 0.0      # 0..100 (0 if unavailable)
    is_trending: bool = False         # on StockTwits' trending board
    # market reaction
    price_pct: float = 0.0           # recent % move
    volume_spike: float = 1.0        # recent vol / avg
    last_price: float = 0.0
    price_ok: bool = False


@dataclass
class MarketContext:
    by_symbol: dict[str, InstrumentSignal] = field(default_factory=dict)
    trending_symbols: list[str] = field(default_factory=list)
    fetched_ts: float = 0.0

    def signal(self, symbol: str) -> InstrumentSignal | None:
        return self.by_symbol.get(symbol)

    # --- persistence ---
    def to_dict(self) -> dict:
        return {
            "by_symbol": {k: asdict(v) for k, v in self.by_symbol.items()},
            "trending_symbols": self.trending_symbols,
            "fetched_ts": self.fetched_ts,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "MarketContext":
        ctx = cls()
        if not d:
            return ctx
        ctx.trending_symbols = d.get("trending_symbols", [])
        ctx.fetched_ts = d.get("fetched_ts", 0.0)
        for k, v in (d.get("by_symbol") or {}).items():
            ctx.by_symbol[k] = InstrumentSignal(**v)
        return ctx


async def build_market_context() -> MarketContext:
    """Fetch every live signal concurrently and assemble per-instrument records."""
    import time

    st_symbols = [m["stocktwits"] for m in INSTRUMENT_MARKETS.values()]
    yahoo_symbols = [m["yahoo"] for m in INSTRUMENT_MARKETS.values()]
    trend_terms = [m["trends"] for m in INSTRUMENT_MARKETS.values()]

    st_snap, reddit_snap, price_snap, trends_map = await asyncio.gather(
        fetch_stocktwits(st_symbols),
        fetch_reddit(),
        fetch_prices(yahoo_symbols),
        fetch_trends(trend_terms),
    )

    trending_upper = {s.upper() for s in st_snap.trending}
    ctx = MarketContext(trending_symbols=st_snap.trending, fetched_ts=time.time())

    for sym, mkt in INSTRUMENT_MARKETS.items():
        sig = InstrumentSignal(symbol=sym)

        buzz = st_snap.get(mkt["stocktwits"])
        if buzz:
            sig.social_velocity = buzz.velocity_per_min
            sig.social_watchers = buzz.watchers
            sig.sentiment = buzz.sentiment
            sig.is_trending = mkt["stocktwits"].upper() in trending_upper

        mentions, velocity, engagement = reddit_snap.mentions(mkt["cashtags"])
        sig.reddit_velocity = velocity
        sig.reddit_engagement = engagement

        sig.trends_interest = trends_map.get(mkt["trends"], 0.0)

        pr = price_snap.get(mkt["yahoo"])
        if pr and pr.ok:
            sig.price_pct = pr.pct_change_recent
            sig.volume_spike = pr.volume_spike
            sig.last_price = pr.last
            sig.price_ok = True

        ctx.by_symbol[sym] = sig

    return ctx
