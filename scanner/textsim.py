"""Tiny pure-Python TF-IDF cosine similarity.

Replaces scikit-learn for the clustering step. The per-scan corpus is small
(at most a few hundred short documents), so a dict-based sparse implementation
is plenty fast and keeps the serverless bundle small and cold-starts quick —
no numpy/scipy/sklearn required.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD_RE = re.compile(r"[a-z0-9$%]+")

# compact English stopword list (enough for headline matching)
_STOP = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "as", "at", "by", "from", "is", "are", "was", "were", "be", "been", "being",
    "it", "its", "this", "that", "these", "those", "his", "her", "their", "our",
    "you", "your", "we", "they", "he", "she", "i", "not", "no", "do", "does",
    "did", "has", "have", "had", "will", "would", "can", "could", "should",
    "may", "might", "must", "after", "before", "over", "into", "amid", "about",
    "what", "it's", "up", "out", "than", "then", "so", "if", "more", "ahead",
}


def tokenize(text: str) -> list[str]:
    """Unigrams + bigrams of significant tokens."""
    words = [t for t in _WORD_RE.findall(text.lower()) if len(t) > 1 and t not in _STOP]
    bigrams = [f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)]
    return words + bigrams


def build_tfidf(docs_tokens: list[list[str]]) -> list[dict[str, float]]:
    """Build L2-normalised sublinear-TF / IDF vectors for a list of token lists."""
    n = len(docs_tokens)
    df: Counter[str] = Counter()
    for toks in docs_tokens:
        for t in set(toks):
            df[t] += 1
    idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}

    vectors: list[dict[str, float]] = []
    for toks in docs_tokens:
        tf = Counter(toks)
        vec = {t: (1.0 + math.log(c)) * idf[t] for t, c in tf.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vectors.append({t: w / norm for t, w in vec.items()})
    return vectors


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity of two L2-normalised sparse vectors."""
    if not a or not b:
        return 0.0
    # iterate over the smaller vector
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())
