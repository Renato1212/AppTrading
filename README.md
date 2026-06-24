# Futures News Scanner

A real-time scanner for **market-moving news**, built for futures traders. It
continuously pulls headlines from many financial-news outlets, recognises when
the *same story* is being published across multiple outlets, and computes a live
**Trending Score** that measures how much market-moving attention each story is
getting right now.

The core idea: a single story on one site is noise. The *same* story hitting
Reuters, CNBC, MarketWatch and five others within minutes — with rising pickup
velocity, a spike in live StockTwits/Reddit chatter on the affected contracts,
**and an actual price move on a volume spike in those futures** — is a tradable
signal. This tool quantifies that, and ranks it in real time.

![board](docs/board.png)

---

## What it measures

For every clustered news **event**, the score (0–100) blends real-time news,
attention and market signals — then multiplies by whether the market is actually
reacting:

| Signal | What it captures | Source |
|--------|------------------|--------|
| **Breadth** | How many distinct outlets publish the story (tier-weighted: wires > aggregators) | distinct outlets in the cluster |
| **News velocity** | How fast new outlets pick it up | outlet-count time series across scans |
| **Social attention** | **Real-time** crowd attention on the event's instruments | StockTwits message velocity + Reddit (WSB/stocks) mention velocity + Google Trends interest |
| **Impact** | Whether it's genuinely market-moving (Fed, CPI, NFP, OPEC, war, crash…) | weighted keyword model |
| **Market confirmation** ⭐ | **Is the related futures contract actually moving, on a volume spike?** Used as a conviction multiplier — the real edge | Yahoo Finance intraday candles (price % move + volume vs average) |
| **Recency** | Fresh stories rank above stale ones | exponential decay (90-min half-life) |

It tags each event with the **futures contracts** it's relevant to (ES, NQ, CL,
GC, ZN, 6E, BTC, …) and, for each, maps to the proxy tickers / Yahoo symbols used
to read live attention and price reaction (`scanner/sources.py` → `INSTRUMENT_MARKETS`).

> **On "pageviews":** there is **no third-party API for real-time per-article
> pageviews** on Bloomberg/CNBC/Reuters/WSJ — those are each outlet's private
> analytics. So instead of faking that number, attention is measured from
> sources that genuinely update in real time and are openly accessible:
> StockTwits message velocity, Reddit mention velocity, and Google Trends. The
> market-confirmation multiplier (is price actually moving?) is what turns
> "lots of chatter" into "lots of chatter the market is trading on."

### How "how many outlets" actually works

Outlets phrase the same event very differently ("Fed" vs "Powell" vs "FOMC",
"rate cut" vs "interest-rate decision"). Plain text similarity badly
under-counts coverage. The scanner clusters stories with a hybrid of:

1. **TF-IDF cosine** over headline + summary (lexical overlap), and
2. **canonical market-entity overlap** — synonyms are normalised to entities
   like `FED`, `RATES`, `OPEC`, `OIL`, `STOCKS` (`scanner/entities.py`), and
   articles sharing a strong entity set are treated as the same story.

The entity signal carries most of the weight; cosine guards against false
merges. This is what lets the scanner correctly say "6 outlets are covering
this" instead of seeing six unrelated headlines.

---

## Quick start (local)

```bash
pip install -r requirements.txt

# Terminal board:
python run.py --once          # single pass, print board, exit
python run.py                 # continuous, scans every 60s
python run.py --demo          # synthetic feeds, no network needed

# Web dashboard + JSON API:
uvicorn app:app --reload      # then open http://localhost:8000
```

The local server runs the same app as the Vercel deployment, but with a local
file-backed store and an in-process background scan loop.

### Demo mode (no network)

If outbound access to news sites is restricted, run with synthetic fixtures so
you can see the full pipeline and dashboard working:

```bash
python run.py --once --demo
SCANNER_DEMO=1 uvicorn app:app          # dashboard with sample data
```

## Deploy to Vercel

The app is Vercel-native: a serverless ASGI function serves the dashboard/API,
**Vercel Cron** runs the scan on a schedule, and a **Redis KV** store keeps the
event set and outlet-history alive between stateless invocations (so velocity
keeps working across scans).

1. **Add a KV store** — in the Vercel dashboard add *Vercel KV* (or the Upstash
   Redis integration) to the project. This sets the env vars the app reads:
   `KV_REST_API_URL` / `KV_REST_API_TOKEN` (or `UPSTASH_REDIS_REST_URL` /
   `UPSTASH_REDIS_REST_TOKEN`). Without them the app falls back to ephemeral
   `/tmp` storage, which won't persist on serverless.
2. **(Recommended) set `CRON_SECRET`** — any random string. The `GET /api/scan`
   cron endpoint then rejects requests without `Authorization: Bearer <secret>`,
   which Vercel Cron sends automatically.
3. **Deploy.** `vercel.json` wires it up:
   - all routes → the `api/index.py` ASGI app,
   - a cron hitting `/api/scan`.

   > **Cron cadence & plans.** The committed schedule is `0 0 * * *` (once a
   > day) because **Vercel Hobby only allows daily crons**. A once-a-day scan
   > isn't really "real-time", so for live cadence either:
   > - **upgrade to Pro** and change the schedule to e.g. `*/2 * * * *`
   >   (every 2 min) in `vercel.json`, or
   > - keep Hobby and trigger `/api/scan` from an external uptime pinger
   >   (e.g. cron-job.org) every minute or two, sending the
   >   `Authorization: Bearer <CRON_SECRET>` header.
   >
   > The scan endpoint itself works at any frequency — only Vercel's *own* cron
   > scheduler is plan-limited.

Everything is stdlib + FastAPI + httpx — no numpy/scipy/sklearn — so the
function bundle stays small and cold-starts fast.

### Go-live checklist (why the board looks empty)

A successful deploy is not enough to see data — two more things matter:

- [ ] **Connect a KV store** (above). Without it the function has nowhere to
      persist scans, so the board stays empty no matter how many times it runs.
- [ ] **Run the first scan** — open `/api/scan` once (or click *Scan now* on the
      empty-state screen). The board populates and the cron keeps it updated.
- [ ] **To view the dashboard**, either open the deployment **while logged into
      your Vercel account**, or turn off **Settings → Deployment Protection →
      Vercel Authentication** so the URL is publicly viewable. (A protected
      deployment returns `403` to anonymous visitors — that's Vercel, not a bug.)

If the board has never been scanned it shows these steps inline instead of a
blank screen.

---

## Web API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Real-time dashboard (auto-refresh every 15s) |
| `GET /api/board?limit=&instrument=&asset=` | Ranked trending board (JSON) |
| `GET /api/event/{id}` | Full detail for one event incl. all articles |
| `GET /api/instruments` | Tracked futures contracts |
| `GET /api/sources` | Configured news outlets |
| `GET /api/stats` | Scan stats |
| `POST /api/scan` | Force an immediate scan |

Example — top energy-market stories right now:

```bash
curl "localhost:8000/api/board?asset=Energy&limit=5"
```

Each event in the response carries its full `breakdown` (breadth, velocity,
attention, impact, recency, outlet count, views, pickup rate) so you can see
*why* a story is trending, not just that it is.

---

## Architecture

```
fetch news (async RSS/Atom)               scanner/fetcher.py + feedparse.py
fetch signals (concurrent, best-effort)   scanner/signals/{stocktwits,reddit,trends,prices}.py
   │   articles + per-instrument market context   scanner/market.py + sources.py
   ▼
cluster (TF-IDF cosine + entity overlap)  scanner/clustering.py + textsim.py
   │   same story across outlets → Event   scanner/entities.py + models.py
   ▼
score (breadth·news velocity·social·impact         scanner/scoring.py
        × market confirmation × recency)
   │
   ▼
persist  (Redis KV / local file)          scanner/store.py + engine.py
   │
   ▼
serve (ranked board, filters)             scanner/webapp.py → app.py / api/index.py
```

- **`scanner/signals/`** — best-effort real-time adapters: `stocktwits.py`
  (message velocity + trending), `reddit.py` (mention velocity), `trends.py`
  (search interest), `prices.py` (price move + volume spike). Any one can be
  down without breaking a scan.
- **`scanner/market.py`** — fetches all signals concurrently and folds them into
  one record per futures contract.

- **`scanner/sources.py`** — outlet feeds (tiered) and the futures-instrument +
  market-impact keyword maps. Add or remove outlets here.
- **`scanner/scoring.py`** — all scoring weights and the normalisation/decay
  curves live here and are easy to tune.
- **`scanner/textsim.py`** — the dependency-free TF-IDF cosine used for
  clustering (replaces scikit-learn).
- **`scanner/store.py` / `engine.py`** — state persistence and the stateless
  scan/read cycle the serverless functions use.
- **`scanner/webapp.py`** — shared FastAPI factory used by both the local server
  (`app.py`) and the Vercel function (`api/index.py`).

Run the offline tests:

```bash
PYTHONPATH=. python tests/test_pipeline.py
PYTHONPATH=. python tests/test_engine.py
```

---

## Notes & limitations

- **Live data requires outbound HTTPS** to the news domains plus
  `api.stocktwits.com`, `www.reddit.com`, `query1.finance.yahoo.com` and
  `trends.google.com`. In a locked-down network (e.g. a policy-restricted CI
  sandbox) those are blocked — use `--demo` / `SCANNER_DEMO=1` there. Every
  signal is best-effort, so partial blocking just degrades the score gracefully
  rather than erroring.
- **No real per-article pageviews exist** from any third-party API (they're each
  outlet's private analytics). Attention is therefore measured from StockTwits +
  Reddit + Google Trends, which are real and real-time. To upgrade to a licensed
  feed later, add an adapter under `scanner/signals/` and fold it into
  `scanner/market.py` — the scoring already consumes a generic `InstrumentSignal`.
- **Google Trends** has no official API and rate-limits datacenter IPs (incl.
  serverless), so it's the least reliable signal and weighted lowest; the score
  leans on StockTwits/Reddit/price when Trends is unavailable.
- **StockTwits/Reddit** use liquid proxy tickers (e.g. SPY for ES, USO for CL)
  since futures themselves get little retail chatter — see `INSTRUMENT_MARKETS`.
- This is a research/monitoring tool, **not trading advice**.
