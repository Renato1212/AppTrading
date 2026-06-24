"""FastAPI app: real-time futures news scanner dashboard + JSON API.

Run:  uvicorn app:app --reload
Then open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scanner.models import Event
from scanner.scanner import NewsScanner
from scanner.sources import INSTRUMENTS, SOURCES

SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "60"))  # seconds between scans
DEMO_MODE = os.getenv("SCANNER_DEMO", "0") in ("1", "true", "yes")

scanner = NewsScanner(interval_seconds=SCAN_INTERVAL, demo=DEMO_MODE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prime the board with one scan, then run the loop in the background.
    await scanner.scan_once()
    task = asyncio.create_task(scanner.run_forever())
    yield
    task.cancel()


app = FastAPI(title="Futures News Scanner", version="1.0.0", lifespan=lifespan)


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


@app.get("/api/board")
def board(
    limit: int = Query(50, ge=1, le=200),
    instrument: str | None = None,
    asset: str | None = None,
):
    """Current ranked trending board."""
    events = scanner.board(limit=limit, instrument=instrument, asset=asset)
    return JSONResponse(
        {
            "generated_ts": time.time(),
            "last_scan_ts": scanner.last_scan_ts,
            "scan_count": scanner.scan_count,
            "scan_interval_s": scanner.interval,
            "total_tracked": len(scanner._ranked),
            "count": len(events),
            "events": [_event_json(e) for e in events],
        }
    )


@app.get("/api/event/{event_id}")
def event_detail(event_id: str):
    ev = scanner.clusterer.events.get(event_id)
    if not ev:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_event_json(ev))


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


@app.get("/api/stats")
def stats():
    events = scanner._ranked
    return {
        "last_scan_ts": scanner.last_scan_ts,
        "scan_count": scanner.scan_count,
        "events_tracked": len(events),
        "outlets_active": len({a.outlet for e in events for a in e.articles}),
        "articles_total": sum(e.article_count for e in events),
        "top_score": events[0].score if events else 0,
    }


@app.post("/api/scan")
async def force_scan():
    """Trigger an immediate scan (useful for demos/testing)."""
    await scanner.scan_once()
    return {"ok": True, "scan_count": scanner.scan_count}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
