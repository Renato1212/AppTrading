"""Google Trends real-time search-interest signal (best-effort).

Search-interest velocity is a real attention signal, but Google Trends has no
official API and frequently rate-limits datacenter IPs (e.g. serverless). So
this adapter is strictly best-effort: on any failure it returns no data and the
score simply leans on the more reliable StockTwits / Reddit / price signals.

It performs the standard unofficial two-step flow: fetch an explore token, then
request the interest-over-time series and read the latest value (0-100).
"""

from __future__ import annotations

import asyncio
import json

import httpx

_HEADERS = {"User-Agent": "Mozilla/5.0 (FuturesNewsScanner/2.0)"}
_EXPLORE = "https://trends.google.com/trends/api/explore"
_IOT = "https://trends.google.com/trends/api/widgetdata/multiline"


def _strip_prefix(text: str) -> str:
    # Google prefixes JSON responses with ")]}'," to thwart hijacking.
    return text[text.find("{"):] if "{" in text else text


async def _interest(client: httpx.AsyncClient, term: str) -> float | None:
    explore_req = {
        "comparisonItem": [{"keyword": term, "geo": "US", "time": "now 1-d"}],
        "category": 0,
        "property": "",
    }
    try:
        r = await client.get(
            _EXPLORE,
            params={"hl": "en-US", "tz": "0", "req": json.dumps(explore_req)},
            headers=_HEADERS,
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        widgets = json.loads(_strip_prefix(r.text)).get("widgets", [])
        tk = next((w for w in widgets if w.get("id") == "TIMESERIES"), None)
        if not tk:
            return None
        r2 = await client.get(
            _IOT,
            params={"hl": "en-US", "tz": "0", "req": json.dumps(tk["request"]), "token": tk["token"]},
            headers=_HEADERS,
            timeout=8.0,
        )
        if r2.status_code != 200:
            return None
        timeline = json.loads(_strip_prefix(r2.text))["default"]["timelineData"]
        if not timeline:
            return None
        return float(timeline[-1]["value"][0])
    except Exception:  # noqa: BLE001
        return None


async def fetch_trends(terms: list[str]) -> dict[str, float]:
    """Map term -> latest interest (0-100). Missing/failed terms are omitted."""
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_interest(client, t) for t in terms])
    return {t: v for t, v in zip(terms, results) if v is not None}
