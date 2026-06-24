"""StockTwits real-time attention signal.

StockTwits is a public stream of trader chatter keyed by ticker ($cashtags). The
rate at which messages are posted about a symbol is a genuine, real-time proxy
for "how much attention is the crowd paying to this right now" — exactly the
kind of measurable attention that per-article pageviews would have given us, but
actually obtainable. No API key required (the public v2 endpoints are used).

We pull, per proxy symbol:
  * message velocity  - messages posted in the last N minutes (the live signal)
  * watcher count     - size of the audience following the symbol
  * sentiment tilt    - share of tagged messages marked Bullish vs Bearish
and, separately, the platform-wide trending symbols.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

_BASE = "https://api.stocktwits.com/api/2"
_HEADERS = {"User-Agent": "Mozilla/5.0 (FuturesNewsScanner/2.0)"}
_RECENT_WINDOW_MIN = 30.0


@dataclass
class SymbolBuzz:
    symbol: str
    messages_recent: int = 0          # messages in the recent window
    velocity_per_min: float = 0.0     # messages/min in the recent window
    watchers: int = 0
    sentiment: float = 0.0            # -1 (bearish) .. +1 (bullish), 0 = neutral/unknown


@dataclass
class StockTwitsSnapshot:
    by_symbol: dict[str, SymbolBuzz] = field(default_factory=dict)
    trending: list[str] = field(default_factory=list)

    def get(self, symbol: str) -> SymbolBuzz | None:
        return self.by_symbol.get(symbol)


async def _fetch_symbol(client: httpx.AsyncClient, symbol: str) -> SymbolBuzz | None:
    url = f"{_BASE}/streams/symbol/{symbol}.json"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=10.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:  # noqa: BLE001 - best-effort
        return None

    messages = data.get("messages", []) or []
    now = time.time()
    cutoff = now - _RECENT_WINDOW_MIN * 60
    recent = 0
    bull = bear = 0
    for m in messages:
        ts = _parse_ts(m.get("created_at"))
        if ts and ts >= cutoff:
            recent += 1
        sentiment = (((m.get("entities") or {}).get("sentiment")) or {}).get("basic")
        if sentiment == "Bullish":
            bull += 1
        elif sentiment == "Bearish":
            bear += 1

    watchers = (data.get("symbol") or {}).get("watchlist_count", 0) or 0
    sent = (bull - bear) / (bull + bear) if (bull + bear) else 0.0
    return SymbolBuzz(
        symbol=symbol,
        messages_recent=recent,
        velocity_per_min=round(recent / _RECENT_WINDOW_MIN, 3),
        watchers=int(watchers),
        sentiment=round(sent, 3),
    )


async def _fetch_trending(client: httpx.AsyncClient) -> list[str]:
    try:
        resp = await client.get(f"{_BASE}/trending/symbols.json", headers=_HEADERS, timeout=10.0)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:  # noqa: BLE001
        return []
    return [s.get("symbol") for s in (data.get("symbols") or []) if s.get("symbol")]


def _parse_ts(raw: str | None) -> float | None:
    if not raw:
        return None
    # StockTwits format: "2026-06-24T14:05:12Z"
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return time.mktime(time.strptime(raw, fmt)) - time.timezone
        except ValueError:
            continue
    return None


async def fetch_stocktwits(symbols: list[str]) -> StockTwitsSnapshot:
    """Fetch buzz for the given proxy symbols plus the trending board."""
    import asyncio

    snapshot = StockTwitsSnapshot()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            _fetch_trending(client),
            *[_fetch_symbol(client, s) for s in symbols],
        )
    snapshot.trending = results[0] or []
    for buzz in results[1:]:
        if buzz is not None:
            snapshot.by_symbol[buzz.symbol] = buzz
    return snapshot
