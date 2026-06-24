"""Synthetic article fixtures for offline demo / testing.

Useful when live feeds are unreachable (e.g. a restrictive network policy) or
for deterministic tests of the clustering + scoring pipeline. Seeds a realistic
mix: one big multi-outlet Fed story, a clustering oil story, and some noise.
"""

from __future__ import annotations

import time

from .market import InstrumentSignal, MarketContext
from .models import Article


def sample_articles(now: float | None = None) -> list[Article]:
    now = now or time.time()

    def art(title, summary, outlet, tier, age_min, views=None):
        return Article(
            title=title,
            summary=summary,
            link=f"https://example.com/{outlet.lower().replace(' ', '')}/{abs(hash(title)) % 10**8}",
            outlet=outlet,
            feed_name="sample",
            tier=tier,
            published_ts=now - age_min * 60,
            fetched_ts=now - age_min * 60,
            views=views,
        )

    return [
        # --- Big breaking macro story: many outlets, high impact (ES/NQ/ZN) ---
        art("Fed holds rates steady but signals a possible rate cut as inflation cools",
            "The Federal Reserve kept interest rates unchanged and Powell hinted at a rate cut, sending the S&P 500 and Nasdaq higher.",
            "Reuters", 1, 8, views=48000),
        art("Powell signals rate cut ahead; stocks rally, Treasury yields fall",
            "Wall Street rallied after the FOMC decision as bond yields dropped on rate cut expectations.",
            "CNBC", 1, 7, views=39000),
        art("Stocks surge as Fed hints at interest rate cut",
            "The S&P 500 jumped after the Federal Reserve signaled an interest rate cut amid cooling inflation.",
            "MarketWatch", 1, 6),
        art("Fed signals rate cut: what it means for markets",
            "The central bank's dovish turn lifted equities and pressured the dollar.",
            "Yahoo Finance", 2, 5, views=12000),
        art("Wall Street climbs on Fed rate cut signal",
            "Stocks soared as the FOMC held rates and Powell opened the door to a cut.",
            "Business Insider", 2, 4),
        art("Federal Reserve holds rates, markets price in September cut",
            "Treasury yields fell and stocks rallied after the Fed decision.",
            "Investing.com", 2, 2),

        # --- Oil story: OPEC, medium breadth (CL) ---
        art("OPEC+ surprises market with output cut, crude oil prices soar",
            "OPEC+ announced a surprise production cut, sending WTI crude oil prices sharply higher.",
            "Reuters", 1, 20, views=22000),
        art("Crude oil jumps as OPEC+ slashes output",
            "Oil prices surged after OPEC+ agreed to cut barrel production.",
            "OilPrice", 2, 18),
        art("Oil price rallies on OPEC supply cut",
            "Brent and WTI climbed as OPEC tightened supply.",
            "Kitco", 2, 12),

        # --- Single-outlet smaller stories (noise) ---
        art("Gold edges higher as dollar weakens",
            "Gold prices ticked up as the US dollar index slipped.",
            "Kitco", 2, 30, views=3000),
        art("Bitcoin tops $80,000 amid crypto rally",
            "Bitcoin surged past a record high as digital assets rallied.",
            "CNBC", 1, 45, views=27000),
        art("Corn futures dip on favorable weather",
            "Corn and wheat grain prices fell on improved crop conditions.",
            "Investing.com", 3, 90),
    ]


def sample_market_context() -> MarketContext:
    """Synthetic real-time signals for offline demo of the full scored board.

    Models a Fed day: equity-index + rates contracts are buzzing on StockTwits,
    trending, and moving on a volume spike (strong market confirmation); oil has
    moderate buzz; quieter names show little reaction.
    """
    ctx = MarketContext(trending_symbols=["SPY", "QQQ", "TLT"], fetched_ts=time.time())

    def sig(symbol, sv, rv, trends, trending, pct, vspike, last, sent=0.0):
        return InstrumentSignal(
            symbol=symbol, social_velocity=sv, social_watchers=0, sentiment=sent,
            reddit_velocity=rv, reddit_engagement=int(rv * 1000), trends_interest=trends,
            is_trending=trending, price_pct=pct, volume_spike=vspike, last_price=last,
            price_ok=True,
        )

    ctx.by_symbol = {
        "ES":  sig("ES", 4.2, 0.42, 88, True, 0.95, 2.6, 5512.5, sent=0.45),
        "NQ":  sig("NQ", 3.6, 0.31, 80, True, 1.20, 2.4, 19550.0, sent=0.40),
        "ZN":  sig("ZN", 1.1, 0.10, 55, True, 0.55, 1.9, 110.4, sent=0.20),
        "CL":  sig("CL", 1.8, 0.18, 60, False, 1.7, 2.1, 78.9, sent=0.10),
        "BTC": sig("BTC", 2.4, 0.22, 70, False, 0.6, 1.3, 81250.0, sent=0.30),
        "GC":  sig("GC", 0.5, 0.04, 30, False, 0.2, 1.05, 2410.0, sent=0.05),
        "ZC":  sig("ZC", 0.1, 0.01, 12, False, -0.3, 0.9, 4.15, sent=-0.10),
        "DX":  sig("DX", 0.3, 0.02, 20, False, -0.4, 1.1, 104.2, sent=-0.05),
    }
    return ctx
