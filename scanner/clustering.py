"""Group articles from different outlets into single 'events'.

The same market-moving story (e.g. a hot CPI print) gets published by many
outlets within minutes. To measure *how many outlets* are covering an event we
first have to recognise that those separate articles are the same story. We do
this with TF-IDF vectors over the headline+summary and greedy cosine-similarity
clustering against running events.
"""

from __future__ import annotations

import re
import time
import uuid

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .entities import entity_overlap, extract_entities
from .models import Article, Event

# Combined similarity blends lexical (TF-IDF cosine) and domain (shared market
# entities) signals. Outlets phrase the same story very differently, so the
# entity overlap carries most of the weight; cosine guards against merging two
# different stories that happen to share one generic entity (e.g. STOCKS).
SIMILARITY_THRESHOLD = 0.32
W_COSINE = 0.45
W_ENTITY = 0.55

_WORD_RE = re.compile(r"[a-z0-9$%]+")


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


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
        event_docs = [_normalize(self.events[eid].headline) for eid in event_ids]
        event_entities = [self._event_entities(self.events[eid]) for eid in event_ids]
        new_docs = [_normalize(a.text) for a in new_articles]
        new_entities = [extract_entities(a.text) for a in new_articles]

        corpus = event_docs + new_docs
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        try:
            matrix = vectorizer.fit_transform(corpus)
        except ValueError:
            # corpus had only stop words; fall back to entity-only matching
            matrix = None

        n_events = len(event_docs)
        # event_id (or "new:<j>") each placed new article landed in, for in-batch matching
        placed_event_of_new: dict[int, str] = {}

        for i, art in enumerate(new_articles):
            row = n_events + i
            best_id, best_sim = None, 0.0

            def cosine(a_row: int, b_row: int) -> float:
                if matrix is None:
                    return 0.0
                return float(cosine_similarity(matrix[a_row], matrix[b_row]).ravel()[0])

            # compare against existing events
            for k, eid in enumerate(event_ids):
                cos = cosine(row, k)
                ent = entity_overlap(new_entities[i], event_entities[k])
                combined = W_COSINE * cos + W_ENTITY * ent
                if combined >= self.threshold and combined > best_sim:
                    best_id, best_sim = eid, combined

            # compare against new articles already placed this batch
            for j in range(i):
                eid = placed_event_of_new.get(j)
                if eid is None:
                    continue
                cos = cosine(row, n_events + j)
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
