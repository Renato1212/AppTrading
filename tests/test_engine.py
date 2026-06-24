"""Tests for serverless state persistence (store + engine round-trip)."""

import asyncio
import os
import tempfile

from scanner.clustering import EventClusterer
from scanner.engine import read_board, run_scan
from scanner.market import MarketContext
from scanner.sample import sample_articles, sample_market_context
from scanner.scoring import score_all
from scanner.store import FileStore


def test_market_context_roundtrip():
    ctx = sample_market_context()
    restored = MarketContext.from_dict(ctx.to_dict())
    assert restored.signal("ES").price_pct == ctx.signal("ES").price_pct
    assert restored.trending_symbols == ctx.trending_symbols


def test_market_confirmation_boosts_score():
    # Same news, scored with vs without a reacting market. The reacting market
    # (sample context: ES/NQ moving on a volume spike) must score higher.
    c1 = EventClusterer(); c1.add_articles(sample_articles())
    c2 = EventClusterer(); c2.add_articles(sample_articles())
    with_ctx = score_all(list(c1.events.values()), sample_market_context())
    without_ctx = score_all(list(c2.events.values()), MarketContext())

    top_with = max(e.score for e in with_ctx)
    top_without = max(e.score for e in without_ctx)
    assert top_with > top_without, "market confirmation should raise the score"


def test_clusterer_state_roundtrip():
    c = EventClusterer()
    c.add_articles(sample_articles())
    state = c.to_state()
    restored = EventClusterer.from_state(state)
    assert len(restored.events) == len(c.events)
    # the big Fed cluster survives serialisation with all its outlets
    biggest = max(restored.events.values(), key=lambda e: e.outlet_count)
    assert biggest.outlet_count >= 5
    # seen-uids rebuilt so re-adding the same batch creates no duplicates
    restored.add_articles(sample_articles())
    assert len(restored.events) == len(c.events)


def test_engine_persists_and_accumulates():
    async def run():
        with tempfile.TemporaryDirectory() as d:
            store = FileStore(os.path.join(d, "state.json"))
            r1 = await run_scan(store, demo=True)
            r2 = await run_scan(store, demo=True)
            assert r1["scan_count"] == 1
            assert r2["scan_count"] == 2
            # second scan loaded prior state instead of duplicating events
            assert r1["events_tracked"] == r2["events_tracked"]
            ranked, meta = await read_board(store)
            assert meta["scan_count"] == 2
            assert ranked and ranked[0].score >= ranked[-1].score

    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all engine tests passed")
