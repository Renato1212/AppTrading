"""Futures trading news scanner.

Tracks market-moving news across many outlets, clusters the same story into
events, and scores each event's real-time trending attention from outlet
breadth, publishing velocity, an engagement proxy, recency and market impact.
"""

from .scanner import NewsScanner

__all__ = ["NewsScanner"]
__version__ = "1.0.0"
