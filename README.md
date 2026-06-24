# Futures News Scanner

A real-time scanner for **market-moving news**, built for futures traders. It
continuously pulls headlines from many financial-news outlets, recognises when
the *same story* is being published across multiple outlets, and computes a live
**Trending Score** that measures how much market-moving attention each story is
getting right now.

The core idea: a single story breaking on one site is noise. The *same* story
hitting Reuters, CNBC, MarketWatch and five others within minutes — with rising
pickup velocity and Fed/CPI/OPEC-grade impact words — is a tradable signal. This
tool quantifies that.

![board](docs/board.png)

---

## What it measures

For every clustered news **event**, the score (0–100) blends five live signals:

| Signal | What it captures | Source |
|--------|------------------|--------|
| **Breadth** | How many distinct outlets are publishing the story (tier-weighted: wires count more than aggregators) | distinct outlets in the cluster |
| **Velocity** | How *fast* new outlets are picking it up — acceleration of coverage | outlet-count time series across scans |
| **Attention** | An engagement / "views" proxy | real view/comment counts where a feed exposes them, else coverage volume |
| **Impact** | Whether it's genuinely market-moving (Fed, CPI, NFP, OPEC, war, crash…) | weighted keyword model |
| **Recency** | Fresh stories rank above stale ones | exponential decay (90-min half-life) |

It also tags each event with the **futures contracts** it's relevant to
(ES, NQ, CL, GC, ZN, 6E, BTC, …) so you can filter the board by asset class.

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
fetch (async, many RSS/Atom feeds)        scanner/fetcher.py + feedparse.py
   │   one Article per outlet pickup       scanner/sources.py   (the outlet list)
   ▼
cluster (TF-IDF cosine + entity overlap)  scanner/clustering.py + textsim.py
   │   same story across outlets → Event   scanner/entities.py + models.py
   ▼
score (breadth·velocity·attention·impact·recency)   scanner/scoring.py
   │
   ▼
persist  (Redis KV / local file)          scanner/store.py + engine.py
   │
   ▼
serve (ranked board, filters)             scanner/webapp.py → app.py / api/index.py
```

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

- **Live feeds require outbound HTTPS** to the news domains in
  `scanner/sources.py`. In a locked-down network (e.g. a policy-restricted CI
  sandbox) those requests are blocked — use `--demo` / `SCANNER_DEMO=1` there.
- True per-article "views" are not exposed by most RSS feeds; where they aren't,
  the scanner uses coverage breadth + volume as the attention proxy. Plugging in
  a paid news/engagement API would make the attention term exact — the hook is
  `Article.views` and `_attention_proxy()` in `scanner/scoring.py`.
- This is a research/monitoring tool, **not trading advice**.
