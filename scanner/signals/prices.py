"""Price / volume reaction signal (the market-confirmation edge).

A news story only matters for trading if the market is actually reacting to it.
We pull recent intraday candles for each futures contract from Yahoo Finance and
measure two things over the last ~30 minutes:

  * price move  - absolute % change (is it moving?)
  * volume spike - latest-bar volume vs the session's average (is it moving on
                   real participation, or just drifting?)

When a news+attention spike lines up with a genuine price+volume reaction in the
related contract, that's the high-conviction signal — used as a score multiplier.
No API key required.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

_HEADERS = {"User-Agent": "Mozilla/5.0 (FuturesNewsScanner/2.0)"}
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=5m"
_RECENT_BARS = 6  # ~30 minutes at 5m bars


@dataclass
class PriceReaction:
    symbol: str
    last: float = 0.0
    pct_change_recent: float = 0.0   # % change over the recent window
    volume_spike: float = 1.0        # latest-window volume / average bar volume
    ok: bool = False


@dataclass
class PriceSnapshot:
    by_symbol: dict[str, PriceReaction] = field(default_factory=dict)

    def get(self, symbol: str) -> PriceReaction | None:
        return self.by_symbol.get(symbol)


async def _fetch_one(client: httpx.AsyncClient, yahoo_symbol: str) -> PriceReaction | None:
    url = _CHART.format(sym=yahoo_symbol)
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=10.0)
        if resp.status_code != 200:
            return None
        result = resp.json()["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [c for c in quote.get("close", []) if c is not None]
        volumes = [v for v in quote.get("volume", []) if v is not None]
    except Exception:  # noqa: BLE001
        return None

    if len(closes) < 2:
        return None

    last = closes[-1]
    window = closes[-_RECENT_BARS:] if len(closes) >= _RECENT_BARS else closes
    start = window[0]
    pct = ((last - start) / start * 100.0) if start else 0.0

    spike = 1.0
    if volumes:
        avg = sum(volumes) / len(volumes)
        recent_v = volumes[-_RECENT_BARS:] if len(volumes) >= _RECENT_BARS else volumes
        recent_avg = sum(recent_v) / len(recent_v)
        spike = (recent_avg / avg) if avg else 1.0

    return PriceReaction(
        symbol=yahoo_symbol,
        last=round(last, 4),
        pct_change_recent=round(pct, 3),
        volume_spike=round(spike, 3),
        ok=True,
    )


async def fetch_prices(yahoo_symbols: list[str]) -> PriceSnapshot:
    snapshot = PriceSnapshot()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch_one(client, s) for s in yahoo_symbols])
    for r in results:
        if r is not None:
            snapshot.by_symbol[r.symbol] = r
    return snapshot
