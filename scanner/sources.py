"""News sources and instrument keyword maps for the futures news scanner.

Sources are public RSS feeds from major financial-news outlets. Each outlet is
treated as a distinct publisher so we can measure how *broadly* a story is being
covered (one of the inputs to the trending score).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    """A single news outlet feed."""

    outlet: str          # human-readable outlet name (the "publisher")
    name: str            # feed/section name
    url: str             # RSS/Atom feed URL
    tier: int = 2        # 1 = wire/primary (Reuters/Bloomberg/WSJ), 2 = major, 3 = aggregator


# A spread of major financial-news RSS feeds. Tier-1 wires carry more weight in
# the breadth calculation because a story breaking on a wire is a stronger
# market-moving signal than the same story on an aggregator.
SOURCES: list[Source] = [
    # --- Tier 1: wires / primary financial press ---
    Source("Reuters", "Business News", "https://www.reutersagency.com/feed/?best-topics=business-finance", tier=1),
    Source("CNBC", "Top News", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", tier=1),
    Source("CNBC", "Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", tier=1),
    Source("MarketWatch", "Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories", tier=1),
    Source("MarketWatch", "Real-time Headlines", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", tier=1),
    Source("Financial Times", "Markets", "https://www.ft.com/markets?format=rss", tier=1),

    # --- Tier 2: major outlets ---
    Source("Yahoo Finance", "Headlines", "https://finance.yahoo.com/news/rssindex", tier=2),
    Source("Investing.com", "News", "https://www.investing.com/rss/news.rss", tier=2),
    Source("Investing.com", "Commodities", "https://www.investing.com/rss/news_11.rss", tier=2),
    Source("Investing.com", "Economy", "https://www.investing.com/rss/news_14.rss", tier=2),
    Source("Seeking Alpha", "Market News", "https://seekingalpha.com/market_currents.xml", tier=2),
    Source("Forbes", "Markets", "https://www.forbes.com/markets/feed/", tier=2),
    Source("Business Insider", "Markets", "https://markets.businessinsider.com/rss/news", tier=2),
    Source("Kitco", "Commodities", "https://www.kitco.com/rss/KitcoNews.xml", tier=2),
    Source("OilPrice", "Energy", "https://oilprice.com/rss/main", tier=2),

    # --- Tier 3: aggregators / wider net ---
    Source("Google News", "Markets", "https://news.google.com/rss/search?q=stock+market+OR+futures+when:1d&hl=en-US&gl=US&ceid=US:en", tier=3),
    Source("Google News", "Fed", "https://news.google.com/rss/search?q=Federal+Reserve+OR+interest+rates+when:1d&hl=en-US&gl=US&ceid=US:en", tier=3),
    Source("Google News", "Oil", "https://news.google.com/rss/search?q=crude+oil+OR+OPEC+when:1d&hl=en-US&gl=US&ceid=US:en", tier=3),
]


# Futures instruments mapped to the keywords that imply a story is relevant to
# them. Used both to tag events with affected contracts and to filter the noise.
INSTRUMENTS: dict[str, dict] = {
    "ES":  {"name": "S&P 500 E-mini",  "asset": "Equity Index",
            "keywords": ["s&p 500", "s&p500", "sp500", "wall street", "stock market", "equities", "dow", "nasdaq", "stocks"]},
    "NQ":  {"name": "Nasdaq-100 E-mini", "asset": "Equity Index",
            "keywords": ["nasdaq", "tech stocks", "big tech", "semiconductor", "nvidia", "apple", "microsoft", "ai stocks"]},
    "YM":  {"name": "Dow E-mini", "asset": "Equity Index",
            "keywords": ["dow jones", "dow industrial", "blue chip"]},
    "RTY": {"name": "Russell 2000 E-mini", "asset": "Equity Index",
            "keywords": ["russell 2000", "small cap", "small-cap"]},
    "CL":  {"name": "WTI Crude Oil", "asset": "Energy",
            "keywords": ["crude oil", "wti", "oil price", "opec", "barrel", "petroleum", "energy prices"]},
    "NG":  {"name": "Natural Gas", "asset": "Energy",
            "keywords": ["natural gas", "lng", "henry hub", "gas prices"]},
    "GC":  {"name": "Gold", "asset": "Metals",
            "keywords": ["gold price", "gold", "bullion", "safe haven", "precious metals"]},
    "SI":  {"name": "Silver", "asset": "Metals",
            "keywords": ["silver price", "silver"]},
    "HG":  {"name": "Copper", "asset": "Metals",
            "keywords": ["copper", "industrial metals"]},
    "ZC":  {"name": "Corn", "asset": "Agriculture",
            "keywords": ["corn", "grain"]},
    "ZW":  {"name": "Wheat", "asset": "Agriculture",
            "keywords": ["wheat", "grain prices"]},
    "ZS":  {"name": "Soybeans", "asset": "Agriculture",
            "keywords": ["soybean", "soybeans", "soy"]},
    "ZN":  {"name": "10-Year T-Note", "asset": "Rates",
            "keywords": ["treasury", "10-year", "treasuries", "bond yields", "yield", "fed funds", "interest rates", "rate cut", "rate hike"]},
    "ZB":  {"name": "30-Year T-Bond", "asset": "Rates",
            "keywords": ["30-year", "long bond"]},
    "6E":  {"name": "Euro FX", "asset": "FX",
            "keywords": ["euro", "ecb", "eur/usd", "eurozone"]},
    "6J":  {"name": "Japanese Yen", "asset": "FX",
            "keywords": ["yen", "boj", "bank of japan", "usd/jpy"]},
    "DX":  {"name": "US Dollar Index", "asset": "FX",
            "keywords": ["dollar index", "dxy", "us dollar", "greenback"]},
    "BTC": {"name": "Bitcoin Futures", "asset": "Crypto",
            "keywords": ["bitcoin", "btc", "crypto", "ethereum", "digital assets"]},
}


# High-impact market-moving terms. Stories containing these get a market-impact
# multiplier because they tend to actually move futures. Weighted by severity.
MARKET_IMPACT_TERMS: dict[str, float] = {
    # Monetary policy / macro data — the biggest movers
    "federal reserve": 1.0, "fed ": 0.9, "fomc": 1.0, "rate cut": 1.0, "rate hike": 1.0,
    "interest rate": 0.8, "powell": 0.8, "cpi": 1.0, "inflation": 0.7, "pce": 0.9,
    "jobs report": 0.9, "nonfarm": 1.0, "payroll": 0.8, "unemployment": 0.7, "gdp": 0.7,
    "ecb": 0.7, "boj": 0.7, "central bank": 0.7,
    # Geopolitics / shocks
    "war": 0.9, "invasion": 0.9, "sanction": 0.7, "opec": 0.9, "tariff": 0.8,
    "ceasefire": 0.7, "strike": 0.5, "attack": 0.7, "shutdown": 0.6,
    # Market action language
    "plunge": 0.8, "soar": 0.7, "crash": 0.9, "selloff": 0.8, "rally": 0.6,
    "surge": 0.6, "tumble": 0.7, "record high": 0.6, "record low": 0.7,
    "recession": 0.8, "default": 0.8, "downgrade": 0.6, "earnings": 0.5,
    "breaking": 0.7, "halt": 0.7, "circuit breaker": 1.0,
}
