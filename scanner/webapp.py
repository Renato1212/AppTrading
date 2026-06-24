"""Shared FastAPI app factory for both the local server and Vercel functions.

The dashboard and JSON API are identical in both deployments; only the state
backend differs (in-process file store locally, Redis KV on Vercel) and how
scans are triggered (background loop locally, Vercel Cron in production).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine import read_board, run_scan
from .models import Event
from .sources import INSTRUMENTS, SOURCES
from .store import Store

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def _event_json(ev: Event) -> dict:
    return {
        "event_id": ev.event_id,
        "headline": ev.headline,
        "score": ev.score,
        "instruments": [
            {"symbol": s, "name": INSTRUMENTS[s]["name"], "asset": INSTRUMENTS[s]["asset"]}
            for s in ev.instruments
            if s in INSTRUMENTS
        ],
        "outlets": sorted(ev.outlets),
        "outlet_count": ev.outlet_count,
        "article_count": ev.article_count,
        "market_impact": ev.market_impact,
        "age_minutes": round(ev.age_minutes, 1),
        "breakdown": ev.score_breakdown,
        "articles": [
            {
                "title": a.title,
                "outlet": a.outlet,
                "link": a.link,
                "tier": a.tier,
                "published_ts": a.published_ts,
            }
            for a in sorted(ev.articles, key=lambda x: x.tier)
        ],
    }


def _filter(events: list[Event], instrument: str | None, asset: str | None) -> list[Event]:
    if instrument:
        events = [e for e in events if instrument.upper() in e.instruments]
    if asset:
        asset_l = asset.lower()
        symbols = {s for s, m in INSTRUMENTS.items() if m["asset"].lower() == asset_l}
        events = [e for e in events if symbols.intersection(e.instruments)]
    return events


def create_app(store: Store, demo: bool = False, min_score: float = 1.0) -> FastAPI:
    app = FastAPI(title="Futures News Scanner", version="2.0.0")
    app.state.store = store
    app.state.demo = demo

    @app.get("/api/board")
    async def board(
        limit: int = Query(50, ge=1, le=200),
        instrument: str | None = None,
        asset: str | None = None,
    ):
        ranked, meta = await read_board(store)
        events = [e for e in ranked if e.score >= min_score]
        events = _filter(events, instrument, asset)[:limit]
        return JSONResponse(
            {
                "last_scan_ts": meta.get("last_scan_ts"),
                "scan_count": meta.get("scan_count", 0),
                "total_tracked": len(ranked),
                "count": len(events),
                "events": [_event_json(e) for e in events],
            }
        )

    @app.get("/api/event/{event_id}")
    async def event_detail(event_id: str):
        ranked, _ = await read_board(store)
        for ev in ranked:
            if ev.event_id == event_id:
                return JSONResponse(_event_json(ev))
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/stats")
    async def stats():
        ranked, meta = await read_board(store)
        return {
            "last_scan_ts": meta.get("last_scan_ts"),
            "scan_count": meta.get("scan_count", 0),
            "events_tracked": len(ranked),
            "outlets_active": len({a.outlet for e in ranked for a in e.articles}),
            "articles_total": sum(e.article_count for e in ranked),
            "top_score": ranked[0].score if ranked else 0,
        }

    @app.get("/api/instruments")
    def instruments():
        return {
            "instruments": [
                {"symbol": s, "name": m["name"], "asset": m["asset"]}
                for s, m in INSTRUMENTS.items()
            ]
        }

    @app.get("/api/sources")
    def sources():
        return {
            "count": len(SOURCES),
            "sources": [
                {"outlet": s.outlet, "name": s.name, "tier": s.tier} for s in SOURCES
            ],
        }

    async def _do_scan():
        return await run_scan(store, demo=app.state.demo)

    @app.post("/api/scan")
    async def scan_post():
        return await _do_scan()

    @app.get("/api/scan")
    async def scan_get(authorization: str | None = Header(default=None)):
        # Vercel Cron sends `Authorization: Bearer $CRON_SECRET`. If a secret is
        # configured, require it so the endpoint can't be triggered by anyone.
        secret = os.getenv("CRON_SECRET")
        if secret and authorization != f"Bearer {secret}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await _do_scan()

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app
