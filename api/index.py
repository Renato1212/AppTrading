"""Vercel serverless entrypoint (ASGI).

Vercel's Python runtime detects the `app` ASGI object and serves it. State is
read from / written to the configured Redis KV store; scans are driven by the
Vercel Cron job defined in vercel.json (which hits GET /api/scan on a schedule).
"""

import sys
from pathlib import Path

# make the repo-root `scanner` package importable from within api/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.store import get_store  # noqa: E402
from scanner.webapp import create_app  # noqa: E402

app = create_app(get_store())
