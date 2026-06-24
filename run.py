"""CLI entrypoint: run the scanner in the terminal without the web UI.

    python run.py            # continuous scan loop, prints the trending board
    python run.py --once     # single pass then exit
    python run.py --interval 30
"""

from __future__ import annotations

import argparse
import asyncio

from scanner.scanner import NewsScanner


async def _main(interval: int, once: bool, demo: bool) -> None:
    scanner = NewsScanner(interval_seconds=interval, demo=demo)
    if once:
        events = await scanner.scan_once()
        print(f"\n=== TRENDING MARKET-MOVING NEWS ({len(events)} events) ===\n")
        for i, ev in enumerate(scanner.board(limit=20), 1):
            tags = ",".join(ev.instruments[:3]) or "-"
            print(f"{i:2}. [{ev.score:5.1f}]  {ev.outlet_count} outlets  ⚡{ev.market_impact:.2f}  [{tags}]")
            print(f"     {ev.headline}")
        return
    await scanner.run_forever()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Futures trading news scanner")
    p.add_argument("--interval", type=int, default=60, help="seconds between scans")
    p.add_argument("--once", action="store_true", help="run a single scan and exit")
    p.add_argument("--demo", action="store_true", help="use synthetic feeds (no network)")
    args = p.parse_args()
    try:
        asyncio.run(_main(args.interval, args.once, args.demo))
    except KeyboardInterrupt:
        print("\nstopped.")
