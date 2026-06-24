"""State persistence for the scanner.

In Vercel's serverless model every request/cron run is a fresh, stateless
invocation, so the event set and outlet-count history (which velocity depends
on) must live in an external store between runs. We use a Redis-compatible KV
over its REST API — works from serverless with no persistent connection.

Locally, when no KV is configured, state falls back to a JSON file so the app
still works end-to-end for development.

Configure with either Vercel KV or Upstash Redis env vars:
    KV_REST_API_URL / KV_REST_API_TOKEN          (Vercel KV)
    UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN   (Upstash)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

STATE_KEY = "futures-news-scanner:state"
TTL_SECONDS = 86400  # auto-expire stale state after a day


class Store:
    async def load(self) -> dict | None:  # pragma: no cover - interface
        raise NotImplementedError

    async def save(self, data: dict) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class RedisRestStore(Store):
    """Redis KV via the Upstash/Vercel-KV REST API (command-array protocol)."""

    def __init__(self, url: str, token: str, key: str = STATE_KEY):
        self.url = url.rstrip("/")
        self.token = token
        self.key = key

    async def _command(self, *args: str) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.url, headers=headers, json=list(args), timeout=10.0)
            resp.raise_for_status()
            return resp.json()

    async def load(self) -> dict | None:
        try:
            result = await self._command("GET", self.key)
        except Exception as exc:  # noqa: BLE001
            print(f"[store] load failed: {type(exc).__name__}: {exc}")
            return None
        raw = result.get("result")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def save(self, data: dict) -> None:
        payload = json.dumps(data, separators=(",", ":"))
        try:
            await self._command("SET", self.key, payload, "EX", str(TTL_SECONDS))
        except Exception as exc:  # noqa: BLE001
            print(f"[store] save failed: {type(exc).__name__}: {exc}")


class FileStore(Store):
    """Local JSON-file fallback for development (no KV configured)."""

    def __init__(self, path: str | Path = ".scanner_state.json"):
        self.path = Path(path)

    async def load(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None

    async def save(self, data: dict) -> None:
        try:
            self.path.write_text(json.dumps(data, separators=(",", ":")))
        except OSError as exc:
            print(f"[store] file save failed: {exc}")


def get_store() -> Store:
    """Pick a store from the environment: Vercel KV / Upstash, else local file."""
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return RedisRestStore(url, token)
    path = os.getenv("SCANNER_STATE_PATH", "/tmp/scanner_state.json")
    return FileStore(path)
