"""Synthetic article fixtures for offline demo / testing.

Useful when live feeds are unreachable (e.g. a restrictive network policy) or
for deterministic tests of the clustering + scoring pipeline. Seeds a realistic
mix: one big multi-outlet Fed story, a clustering oil story, and some noise.
"""

from __future__ import annotations

import time

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
