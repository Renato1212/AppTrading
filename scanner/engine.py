"""Stateless scan/read engine used by the serverless (Vercel) deployment.

Unlike `NewsScanner` (which keeps state in memory for the long-running local
process), these functions load state from the store, mutate it, and persist it
back — so each isolated serverless invocation continues where the last left off.
The Vercel Cron job calls `run_scan`; the dashboard/API calls `read_board`.
"""

from __future__ import annotations

import time

from .clustering import EventClusterer
from .fetcher import fetch_all
from .models import Event
from .scoring import score_all
from .store import Store


async def run_scan(store: Store, demo: bool = False) -> dict:
    """Fetch -> cluster -> persist. Returns a small summary dict."""
    state = await store.load()
    clusterer = EventClusterer.from_state(state)

    if demo:
        from .sample import sample_articles
        articles = sample_articles()
    else:
        articles = await fetch_all()

    clusterer.add_articles(articles)

    meta = (state or {}).get("meta", {})
    meta = {
        "last_scan_ts": time.time(),
        "scan_count": meta.get("scan_count", 0) + 1,
    }
    new_state = clusterer.to_state()
    new_state["meta"] = meta
    await store.save(new_state)

    ranked = score_all(list(clusterer.events.values()))
    return {
        "ok": True,
        "scan_count": meta["scan_count"],
        "events_tracked": len(ranked),
        "articles_ingested": len(articles),
        "top_score": ranked[0].score if ranked else 0,
    }


async def read_board(store: Store) -> tuple[list[Event], dict]:
    """Load persisted state and return freshly-scored, ranked events + meta.

    Scoring happens on read so recency decay reflects the current time even if
    no new scan has run since the last cron tick.
    """
    state = await store.load()
    clusterer = EventClusterer.from_state(state)
    ranked = score_all(list(clusterer.events.values()))
    meta = (state or {}).get("meta", {})
    return ranked, meta
