"""The scanner orchestrator: fetch -> cluster -> score on a repeating loop."""

from __future__ import annotations

import asyncio
import time

from .clustering import EventClusterer
from .fetcher import fetch_all
from .market import build_market_context
from .models import Event
from .scoring import score_all


class NewsScanner:
    """Runs the ingest/score loop and exposes the current ranked event board."""

    def __init__(self, interval_seconds: int = 60, min_score: float = 1.0, demo: bool = False):
        self.interval = interval_seconds
        self.min_score = min_score
        self.demo = demo
        self.clusterer = EventClusterer()
        self.last_scan_ts: float = 0.0
        self.scan_count: int = 0
        self._ranked: list[Event] = []
        self._lock = asyncio.Lock()

    async def scan_once(self) -> list[Event]:
        """Run a single fetch/cluster/score pass and refresh the board."""
        if self.demo:
            from .sample import sample_articles, sample_market_context
            articles = sample_articles()
            context = sample_market_context()
        else:
            articles = await fetch_all()
            context = await build_market_context()
        async with self._lock:
            self.clusterer.add_articles(articles)
            now = time.time()
            self._ranked = score_all(list(self.clusterer.events.values()), context, now)
            self.last_scan_ts = now
            self.scan_count += 1
        return self._ranked

    async def run_forever(self) -> None:
        while True:
            try:
                await self.scan_once()
                board = self.board(limit=5)
                print(f"[scan #{self.scan_count}] {len(self._ranked)} events tracked. Top:")
                for ev in board:
                    tags = ",".join(ev.instruments[:3]) or "-"
                    print(f"   {ev.score:5.1f}  [{tags:<12}] {ev.outlet_count} outlets  {ev.headline[:70]}")
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                print(f"[scan] error: {type(exc).__name__}: {exc}")
            await asyncio.sleep(self.interval)

    def board(self, limit: int = 50, instrument: str | None = None, asset: str | None = None) -> list[Event]:
        """Current ranked events, optionally filtered by instrument/asset class."""
        from .sources import INSTRUMENTS

        events = [e for e in self._ranked if e.score >= self.min_score]
        if instrument:
            events = [e for e in events if instrument.upper() in e.instruments]
        if asset:
            asset_l = asset.lower()
            symbols = {s for s, m in INSTRUMENTS.items() if m["asset"].lower() == asset_l}
            events = [e for e in events if symbols.intersection(e.instruments)]
        return events[:limit]
