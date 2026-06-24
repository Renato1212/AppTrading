"""Local FastAPI server for the futures news scanner.

Runs the same app as the Vercel deployment (scanner.webapp.create_app) but with
a local file-backed store and an in-process background scan loop instead of
Vercel Cron.

Run:  uvicorn app:app --reload     then open http://localhost:8000
Demo: SCANNER_DEMO=1 uvicorn app:app
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from scanner.engine import run_scan
from scanner.store import get_store
from scanner.webapp import create_app

SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "60"))
DEMO_MODE = os.getenv("SCANNER_DEMO", "0") in ("1", "true", "yes")

store = get_store()


async def _scan_loop():
    while True:
        try:
            await run_scan(store, demo=DEMO_MODE)
        except Exception as exc:  # noqa: BLE001
            print(f"[scan] error: {type(exc).__name__}: {exc}")
        await asyncio.sleep(SCAN_INTERVAL)


@asynccontextmanager
async def lifespan(_app):
    await run_scan(store, demo=DEMO_MODE)   # prime the board
    task = asyncio.create_task(_scan_loop())
    yield
    task.cancel()


app = create_app(store, demo=DEMO_MODE)
app.router.lifespan_context = lifespan
