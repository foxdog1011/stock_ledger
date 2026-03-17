# stock_ledger

A full-stack personal portfolio tracker and investment research platform — built from a raw SQLite core library up through a REST API and an interactive Next.js dashboard.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)
![Tests](https://img.shields.io/badge/tests-336-brightgreen)
![Docker](https://img.shields.io/badge/Docker-compose-blue)

---

## Highlights

- **End-to-end ownership** — pure-Python core library → 30+ REST endpoints → TypeScript frontend, no third-party portfolio SDK
- **Domain-Driven Design** — separate `domain/` layer decouples business logic (risk, execution, overview) from API routing and persistence
- **Quantitative analytics** — CAGR, Sharpe ratio, max drawdown, VaR, volatility, beta; benchmark comparison with tracking error, information ratio, and correlation vs. 0050 / SPY / QQQ / TAIEX
- **Investment research pipeline** — Universe (company DB) → Watchlist (investment thesis) → Catalyst (event tracking) → Daily Digest (auto-generated report)
- **Multi-provider quote engine** — pluggable `PriceProvider` ABC with TWSE, FinMind, and Yahoo Finance backends; APScheduler cron runs daily at 18:00 TST; background refresh fires automatically on every trade
- **Tax-aware P&L** — commission and transaction tax flow into cost basis; lot-level FIFO/LIFO/HIFO breakdown; loss-offsetting simulation for tax-loss harvesting
- **336 unit tests** across 13 test files covering domain services, API integration, and CSV import validation

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js 14  ·  TypeScript  ·  TanStack Query v5  ·  shadcn │
│  /overview /portfolio /positions /lots /universe /watchlist  │
│  /catalyst  /digest  /offsetting  /quotes  /settings  …     │
└─────────────────────────┬───────────────────────────────────┘
                          │  HTTP  (server-side proxy, no CORS)
┌─────────────────────────▼───────────────────────────────────┐
│  FastAPI  ·  30+ endpoints  ·  15 routers                    │
│  APScheduler  (daily quote refresh cron @ 18:00 Asia/Taipei) │
│  BackgroundTasks  (auto-refresh on trade POST)               │
└──────┬──────────────────┬──────────────────┬────────────────┘
       │                  │                  │
  domain/ layer      ledger/ library    providers/
  (DDD services)     (pure Python core)  TWSE · FinMind · Yahoo
       │                  │
       └──────────────────┴──── SQLite  (Docker named volume)
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Pure Python `ledger/` library with zero web dependencies | Independently testable; can be used as a CLI or imported without running the API |
| `domain/` layer separate from `apps/api/routers/` | Routers only handle HTTP concerns; business logic is framework-agnostic |
| Pluggable `PriceProvider` ABC | Swap or add data sources without touching the scheduler or refresh service |
| Next.js server-side `API_URL` proxy | Eliminates CORS; frontend never needs direct access to the API port |
| APScheduler + `BackgroundTasks` for quotes | Scheduled refresh at market close; per-trade refresh runs in background without blocking the response |

---

## Quick Start (Docker)

```bash
docker compose up -d
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3001 |
| API + Swagger | http://localhost:8000/docs |

Data persists in the named Docker volume `ledger_data` — rebuilding images does **not** lose data.

Seed realistic demo data from the dashboard FAB button or:

```bash
curl -X POST http://localhost:8000/api/demo/seed
```

---

## Local Development

**Prerequisites:** Python 3.11+, Node.js 18+

```bash
# 1. Python dependencies
pip install -r apps/api/requirements.txt

# 2. Start the API
DB_PATH=data/ledger.db uvicorn apps.api.main:app --reload --port 8000

# 3. Start the frontend (new terminal)
cd apps/web && API_URL=http://localhost:8000 npm run dev

# 4. Run tests
python -m pytest tests/          # 336 tests
```

---

## Feature Walkthrough

### Portfolio Analytics

`/portfolio` aggregates a real-time snapshot: cash, market value, total equity, unrealized and realized P&L. The equity curve supports D / W / ME frequency with a dual-axis chart (equity + cumulative return %).

`GET /api/perf/summary` returns CAGR, Sharpe ratio, and max drawdown.
`GET /api/risk/metrics` returns VaR (95%), annualized volatility, and beta.

### Benchmark Comparison

Bootstrap historical prices from Yahoo Finance (no API key needed) for 0050, TAIEX, SPY, QQQ, or any ticker into the local `prices` table. The compare endpoint aligns the portfolio equity curve with the benchmark series and computes:

- Excess return
- Tracking error (annualized)
- Pearson correlation
- Information ratio

### Investment Research Pipeline

| Stage | Endpoint group | Purpose |
|---|---|---|
| Universe | `/api/universe` | Company master: sector, industry, business model, peer relationships |
| Watchlist | `/api/watchlist` | Curated lists with per-symbol thesis, catalyst, and status |
| Catalyst | `/api/catalyst` | Event log (earnings, guidance, macro) with Plan A/B/C/D scenarios and price targets |
| Digest | `/api/digest` | Auto-generated daily report: P&L, top movers, upcoming catalysts, rebalance alerts |

### Execution Tools

- **Cost impact analysis** — before adding to a position, see how the new buy shifts your average cost and unrealized P&L
- **Lot viewer** — FIFO/LIFO/HIFO lot breakdown with per-lot unrealized % and underwater % visualized as a bubble chart
- **Loss offsetting simulation** — list all losing open positions, check available realized gains inventory, simulate selling a position to crystallize a loss and offset gains for tax purposes

### Quote Engine

The `PriceProvider` ABC is implemented by three backends:

| Provider | Coverage | Auth |
|---|---|---|
| `TWSeProvider` | TWSE listed + OTC (台灣) | None |
| `FinMindProvider` | Taiwan stock history | `FINMIND_TOKEN` |
| `YahooProvider` | US, HK, global | None |
| `SmartProvider` | Auto-routes by ticker pattern | — |

Refresh runs:
1. **Daily cron** at 18:00 Asia/Taipei via APScheduler
2. **On trade** — `POST /api/trades` triggers a background refresh (`skip_if_fresh=True`)
3. **On demand** — `POST /api/quotes/refresh`

All runs are logged to `quote_refresh_log` with timestamp, provider, inserted/skipped counts, and trigger type.

### Data Operations

| Feature | Detail |
|---|---|
| Soft delete | `is_void` flag on both `cash_entries` and `trades`; history is never destroyed |
| CSV import | `dry_run=true` previews insert/skip/error counts before committing |
| CSV export | Trades, cash, quotes |
| DB backup / restore | Download and upload the raw SQLite file from `/settings` |

---

## API Reference

### Cash

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/cash` | Deposit or withdraw |
| `GET` | `/api/cash/balance` | Balance at a point in time |
| `GET` | `/api/cash/tx` | Transaction history (`?include_void=`) |
| `PATCH` | `/api/cash/{id}/void` | Soft-delete |

### Trades

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/trades` | Record a buy or sell (cash adjusted automatically) |
| `GET` | `/api/trades` | Trade history (`?symbol=&include_void=`) |
| `PATCH` | `/api/trades/{id}/void` | Soft-delete |

### Positions & Equity

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/positions` | Holdings with avg cost, unrealized/realized P&L, cost impact |
| `GET` | `/api/lots/{symbol}` | FIFO/LIFO/HIFO lot breakdown |
| `GET` | `/api/equity/snapshot` | Point-in-time cash / market value / total equity |
| `GET` | `/api/equity/curve` | Equity curve (`?freq=ME\|W\|D`) |

### Analytics

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/overview` | Dashboard aggregation (snapshot + catalysts + alerts) |
| `GET` | `/api/perf/summary` | CAGR, Sharpe, max drawdown |
| `GET` | `/api/risk/metrics` | VaR, volatility, beta |
| `GET` | `/api/rebalance/check` | Concentration and cash-level alerts |

### Benchmark

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/benchmark/series` | Benchmark price series + cumulative return |
| `GET` | `/api/benchmark/compare` | Portfolio vs. benchmark with metrics |
| `POST` | `/api/benchmark/bootstrap` | Fetch historical data from Yahoo Finance into local DB |
| `GET` | `/api/benchmark/bootstrap/status` | Last bootstrap run log |

### Execution

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/execution/offset/losing` | All open losing positions |
| `GET` | `/api/execution/offset/profit-inventory` | Realized gains available to offset |
| `GET` | `/api/execution/offset/simulate/{symbol}` | Simulate crystallizing a loss |

### Quotes

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/quotes/manual` | Add a manual closing price |
| `GET` | `/api/quotes/last` | Latest price + source for a symbol |
| `GET` | `/api/quotes/todo` | Symbols with missing or stale quotes |
| `POST` | `/api/quotes/refresh` | Trigger a provider refresh |
| `GET` | `/api/quotes/refresh/status` | Last refresh run log |
| `GET` | `/api/quotes/provider` | Configured provider info |

### Universe & Watchlist

| Method | Path | Description |
|---|---|---|
| `POST/GET` | `/api/universe/companies` | Company master CRUD |
| `GET` | `/api/universe/companies/{symbol}` | Company detail + relationships |
| `POST/GET` | `/api/watchlist/lists` | Watchlist CRUD |
| `POST/GET` | `/api/watchlist/lists/{id}/items` | Watchlist items with thesis |

### Catalyst & Digest

| Method | Path | Description |
|---|---|---|
| `POST/GET` | `/api/catalyst` | Create and list catalyst events |
| `PATCH` | `/api/catalyst/{id}` | Update event status |
| `PUT` | `/api/catalyst/{id}/scenario` | Attach Plan A/B/C/D + price targets |
| `POST` | `/api/digest/generate` | Generate daily digest |
| `GET` | `/api/digest/{date}` | Retrieve a digest by date |

### Import / Export / Backup

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/export/{trades\|cash\|quotes}.csv` | Download as CSV |
| `POST` | `/api/import/{trades\|cash\|quotes}.csv` | Upload CSV (`?dry_run=true`) |
| `GET` | `/api/backup/db` | Download SQLite file |
| `POST` | `/api/restore/db` | Restore from uploaded file |

---

## Frontend Pages

| Route | Description |
|---|---|
| `/overview` | Unified dashboard: snapshot, catalyst feed, rebalance alerts |
| `/portfolio` | Equity curve, benchmark comparison, donut allocation |
| `/positions` | Holdings with cost impact analysis |
| `/lots/[symbol]` | Lot-level breakdown + bubble chart |
| `/universe` | Company research database |
| `/watchlist` | Investment thesis tracker |
| `/catalyst` | Event log + scenario planner |
| `/digest` | Daily portfolio report history |
| `/offsetting` | Tax-loss harvesting simulator |
| `/trades` | Trade history with void support |
| `/cash` | Cash ledger with void support |
| `/quotes` | Manual price entry |
| `/import` | CSV upload with dry-run preview |
| `/settings` | Provider config, export, backup / restore |

---

## Project Structure

```
stock_ledger/
├── domain/                  # Domain layer (DDD) — framework-agnostic
│   ├── overview/            #   Dashboard aggregation service
│   ├── execution/           #   Loss-offsetting simulation
│   ├── portfolio/           #   Portfolio-level calculations
│   ├── risk/                #   Risk metric computation
│   ├── universe/            #   Company research domain
│   └── watchlist/           #   Watchlist and thesis tracking
├── ledger/                  # Core Python library (no web deps)
│   ├── db.py                #   SQLite connection + schema + migrations
│   ├── ledger.py            #   StockLedger class
│   └── equity.py            #   equity_curve(), print_curve(), plot_curve()
├── apps/
│   ├── api/                 # FastAPI application
│   │   ├── providers/       #   PriceProvider ABC + TWSE, FinMind, Yahoo, Auto
│   │   ├── services/        #   QuotesRefreshService
│   │   ├── routers/         #   15 route modules
│   │   ├── config.py        #   Environment config
│   │   ├── deps.py          #   FastAPI dependencies
│   │   └── main.py          #   App factory + APScheduler lifespan
│   └── web/                 # Next.js 14 frontend
│       └── src/
│           ├── app/         #   14 page routes
│           ├── components/  #   Charts, forms, FAB, shadcn/ui
│           ├── hooks/       #   TanStack Query hooks + mutations
│           └── lib/         #   api.ts, types.ts, format.ts
├── tests/                   # 336 tests across 13 files
├── docker-compose.yml
└── data/                    # SQLite DB (auto-created)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Core library | Python 3.11, SQLite (stdlib only) |
| Backend | FastAPI, Uvicorn, Pandas, APScheduler |
| Frontend | Next.js 14, TypeScript, TanStack Query v5, Recharts, Tailwind CSS, shadcn/ui |
| Testing | Python `unittest` (336 tests, 13 files) |
| Container | Docker, Docker Compose |

---

## Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `DB_PATH` | API | `data/ledger.db` | SQLite file path |
| `API_URL` | Web | `http://localhost:8000` | FastAPI base URL (server-side only) |
| `QUOTE_PROVIDER` | API | `auto` | `twse` \| `finmind` \| `yahoo` \| `auto` |
| `FINMIND_TOKEN` | API | _(empty)_ | Required only for FinMind provider |
| `AUTO_REFRESH_QUOTES_ON_TRADE` | API | `1` | Set to `0` to disable background refresh on trade |
| `TZ` | API | `Asia/Taipei` | Scheduler timezone |
