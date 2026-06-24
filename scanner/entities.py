"""Canonical market-entity extraction for robust story clustering.

Different outlets describe the same event with different words: "Fed" vs
"Federal Reserve" vs "Powell" vs "FOMC". Plain TF-IDF treats those as unrelated
tokens, so it badly under-clusters financial news. We fix this by mapping known
synonyms onto a small set of canonical entity tags. Two articles that share a
strong set of entities are very likely the same story — a signal we blend into
the clustering similarity.
"""

from __future__ import annotations

# canonical_tag -> list of surface phrases that imply it
ENTITY_SYNONYMS: dict[str, list[str]] = {
    "FED":         ["federal reserve", "the fed", "fed ", "fomc", "powell", "central bank rate"],
    "RATES":       ["rate cut", "rate hike", "interest rate", "rate decision", "rates steady", "rate path", "basis points"],
    "INFLATION":   ["inflation", "cpi", "pce", "consumer price", "core prices"],
    "JOBS":        ["jobs report", "nonfarm", "payroll", "unemployment", "labor market"],
    "GDP":         ["gdp", "gross domestic", "economic growth"],
    "OPEC":        ["opec", "opec+"],
    "OIL":         ["crude oil", "crude", "wti", "brent", "oil price", "oil prices", "barrel", "petroleum"],
    "NATGAS":      ["natural gas", "lng", "henry hub"],
    "GOLD":        ["gold price", "gold", "bullion", "precious metal"],
    "SILVER":      ["silver"],
    "COPPER":      ["copper"],
    "STOCKS":      ["s&p 500", "sp500", "wall street", "stock market", "stocks", "equities", "nasdaq", "dow"],
    "TREASURIES":  ["treasury", "treasuries", "bond yield", "10-year", "yields fall", "yields rise"],
    "DOLLAR":      ["dollar index", "us dollar", "greenback", "dxy"],
    "EURO":        ["euro", "ecb", "eurozone"],
    "YEN":         ["yen", "boj", "bank of japan"],
    "CRYPTO":      ["bitcoin", "btc", "ethereum", "crypto", "digital asset"],
    "CORN":        ["corn"],
    "WHEAT":       ["wheat"],
    "SOY":         ["soybean", "soybeans", "soy"],
    "WAR":         ["war", "invasion", "missile", "attack", "ceasefire", "conflict"],
    "TARIFF":      ["tariff", "trade war", "import duties"],
    "SANCTION":    ["sanction", "embargo"],
    "EARNINGS":    ["earnings", "profit beat", "revenue miss", "guidance"],
}


def extract_entities(text: str) -> frozenset[str]:
    """Return the set of canonical market entities mentioned in the text."""
    low = text.lower()
    found = set()
    for tag, phrases in ENTITY_SYNONYMS.items():
        if any(p in low for p in phrases):
            found.add(tag)
    return frozenset(found)


def entity_overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """Weighted Jaccard overlap between two entity sets (0..1).

    A near-empty intersection means different stories; sharing the rarer,
    more specific entities (e.g. OPEC) is a stronger same-story signal than
    sharing a generic one (e.g. STOCKS), but plain Jaccard is robust enough
    here and keeps the model simple and predictable.
    """
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0
