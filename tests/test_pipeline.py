"""Offline tests for the clustering + scoring pipeline (no network needed)."""

import time

from scanner.clustering import EventClusterer
from scanner.entities import entity_overlap, extract_entities
from scanner.sample import sample_articles
from scanner.scoring import score_all


def test_entity_extraction():
    ents = extract_entities("Fed signals a rate cut as inflation cools, stocks rally")
    assert "FED" in ents
    assert "RATES" in ents
    assert "INFLATION" in ents
    assert "STOCKS" in ents


def test_entity_overlap_bounds():
    a = frozenset({"FED", "RATES", "STOCKS"})
    b = frozenset({"FED", "RATES", "TREASURIES"})
    assert 0.0 < entity_overlap(a, b) < 1.0
    assert entity_overlap(a, a) == 1.0
    assert entity_overlap(a, frozenset()) == 0.0


def test_clustering_merges_same_story_across_outlets():
    clusterer = EventClusterer()
    clusterer.add_articles(sample_articles())
    events = list(clusterer.events.values())

    # The six Fed articles from six outlets must collapse into one event.
    fed = max(events, key=lambda e: e.outlet_count)
    assert fed.outlet_count >= 5, f"Fed story under-clustered: {fed.outlet_count} outlets"

    # OPEC oil story should cluster its three outlets together too.
    oil = [e for e in events if "OPEC" in extract_entities(e.headline) or "oil" in e.headline.lower()]
    assert any(e.outlet_count >= 3 for e in oil), "oil story did not cluster"

    # Distinct stories must NOT be merged into the Fed cluster.
    assert fed.outlet_count <= 7


def test_scoring_ranks_broad_high_impact_first():
    clusterer = EventClusterer()
    clusterer.add_articles(sample_articles())
    ranked = score_all(list(clusterer.events.values()), time.time())

    assert ranked[0].score >= ranked[-1].score
    # The broadly-covered, high-impact Fed story should top the board.
    assert ranked[0].outlet_count >= 5
    assert ranked[0].market_impact > 0.5
    # All scores are within the 0..100 band.
    assert all(0 <= e.score <= 100 for e in ranked)


def test_instrument_tagging():
    clusterer = EventClusterer()
    clusterer.add_articles(sample_articles())
    score_all(list(clusterer.events.values()), time.time())
    oil = [e for e in clusterer.events.values() if "oil" in e.headline.lower()]
    assert oil and "CL" in oil[0].instruments


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
