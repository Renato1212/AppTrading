"""Group articles from different outlets into single 'events'.

The same market-moving story (e.g. a hot CPI print) gets published by many
outlets within minutes. To measure *how many outlets* are covering an event we
first have to recognise that those separate articles are the same story. We do
this with TF-IDF vectors over the headline+summary and greedy cosine-similarity
clustering against running events, blended with shared market-entity overlap.
"""

from __future__ import annotations

import time
import uuid

from .entities import entity_overlap, extract_entities
from .models import Article, Event
from .textsim import build_tfidf, cosine, tokenize

# Combined similarity blends lexical (TF-IDF cosine) and domain (shared market
# entities) signals. Outlets phrase the same story very differently, so the
# entity overlap carries most of the weight; cosine guards against merging two
# different stories that happen to share one generic entity (e.g. STOCKS).
SIMILARITY_THRESHOLD = 0.32
W_COSINE = 0.45
W_ENTITY = 0.55


class EventClusterer:
    """Maintains a running set of events and assigns new articles to them."""

    def __init__(self, threshold: float = SIMILARITY_THRESHOLD, retention_hours: float = 12.0):
        self.threshold = threshold
        self.retention_seconds = retention_hours * 3600
        self.events: dict[str, Event] = {}
        self._seen_uids: set[str] = set()

    def _expire_old(self) -> None:
        cutoff = time.time() - self.retention_seconds
        stale = [eid for eid, ev in self.events.items() if ev.last_update_ts < cutoff]
        for eid in stale:
            for art in self.events[eid].articles:
                self._seen_uids.discard(art.uid)
            del self.events[eid]

    def add_articles(self, articles: list[Article]) -> None:
        """Ingest a batch of freshly fetched articles into the event set."""
        self._expire_old()
        now = time.time()

        new_articles = [a for a in articles if a.uid not in self._seen_uids]
        if not new_articles:
            self._snapshot_history(now)
            return

        # Build a TF-IDF space over existing event headlines + the new articles
        # so we can match new articles to running events (and to each other).
        event_ids = list(self.events.keys())
        event_entities = [self._event_entities(self.events[eid]) for eid in event_ids]
        new_entities = [extract_entities(a.text) for a in new_articles]

        event_tokens = [tokenize(self.events[eid].headline) for eid in event_ids]
        new_tokens = [tokenize(a.text) for a in new_articles]
        vectors = build_tfidf(event_tokens + new_tokens)

        n_events = len(event_ids)
        event_vecs = vectors[:n_events]
        new_vecs = vectors[n_events:]
        # which event each placed new article landed in, for in-batch matching
        placed_event_of_new: dict[int, str] = {}

        for i, art in enumerate(new_articles):
            best_id, best_sim = None, 0.0

            # compare against existing events
            for k, eid in enumerate(event_ids):
                cos = cosine(new_vecs[i], event_vecs[k])
                ent = entity_overlap(new_entities[i], event_entities[k])
                combined = W_COSINE * cos + W_ENTITY * ent
                if combined >= self.threshold and combined > best_sim:
                    best_id, best_sim = eid, combined

            # compare against new articles already placed this batch
            for j in range(i):
                eid = placed_event_of_new.get(j)
                if eid is None:
                    continue
                cos = cosine(new_vecs[i], new_vecs[j])
                ent = entity_overlap(new_entities[i], new_entities[j])
                combined = W_COSINE * cos + W_ENTITY * ent
                if combined >= self.threshold and combined > best_sim:
                    best_id, best_sim = eid, combined

            if best_id is not None:
                self._attach(self.events[best_id], art, now)
                placed_event_of_new[i] = best_id
            else:
                ev = self._create_event(art, now)
                placed_event_of_new[i] = ev.event_id

        self._snapshot_history(now)

    # --- helpers ---------------------------------------------------------
    def _event_entities(self, ev: Event) -> frozenset[str]:
        """Entity signature of an event, taken from its representative article."""
        best = min(ev.articles, key=lambda a: (a.tier, a.published_ts))
        return extract_entities(best.text)

    def _create_event(self, art: Article, now: float) -> Event:
        eid = uuid.uuid4().hex[:12]
        ev = Event(
            event_id=eid,
            headline=art.title,
            articles=[art],
            first_seen_ts=art.fetched_ts,
            last_update_ts=now,
        )
        self.events[eid] = ev
        self._seen_uids.add(art.uid)
        return ev

    def _attach(self, ev: Event, art: Article, now: float) -> None:
        ev.articles.append(art)
        ev.last_update_ts = now
        self._seen_uids.add(art.uid)
        # Prefer the highest-tier (lowest number), earliest headline as the label.
        best = min(ev.articles, key=lambda a: (a.tier, a.published_ts))
        ev.headline = best.title

    def _snapshot_history(self, now: float) -> None:
        """Record the current distinct-outlet count for each event.

        This time series is what the scorer uses to compute publishing velocity
        (how fast new outlets are picking the story up).
        """
        for ev in self.events.values():
            count = ev.outlet_count
            if not ev.outlet_history or ev.outlet_history[-1][1] != count:
                ev.outlet_history.append((now, count))
            # keep history bounded
            if len(ev.outlet_history) > 200:
                ev.outlet_history = ev.outlet_history[-200:]

    # --- persistence -----------------------------------------------------
    def to_state(self) -> dict:
        """Serialise the running event set for storage between invocations."""
        return {"events": [ev.to_dict() for ev in self.events.values()]}

    @classmethod
    def from_state(cls, state: dict | None) -> "EventClusterer":
        """Rebuild a clusterer from previously stored state."""
        clusterer = cls()
        if not state:
            return clusterer
        for ev_dict in state.get("events", []):
            ev = Event.from_dict(ev_dict)
            clusterer.events[ev.event_id] = ev
            for art in ev.articles:
                clusterer._seen_uids.add(art.uid)
        return clusterer
