# stock_ledger

SQLite-backed personal stock portfolio tracker with a FastAPI REST backend and Next.js dashboard.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![Docker](https://img.shields.io/badge/Docker-compose-blue)

---

## Features

- **Portfolio tracking** – cash ledger, buy/sell trades, unrealized & realized P&L
- **Mark-to-market** – manual price quotes; falls back to last trade price automatically
- **Equity curve** – daily / weekly / monthly snapshots with cumulative return %
- **Performance metrics** – Sharpe ratio, max drawdown, CAGR via `/api/perf/summary`
- **Risk metrics** – VaR, volatility, beta via `/api/risk/metrics`
- **Rebalance alerts** – concentration & cash-level warnings
- **CSV import / export** – trades, cash, quotes
- **DB backup / restore** – single-click download and upload via the Settings page
- **Void transactions** – soft-delete cash entries and trades without losing history
- **Demo seed** – one-click realistic dataset for exploration

---

## Quick Start (Docker)

```bash
docker compose up -d
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3001 |
| API (Swagger) | http://localhost:8000/docs |

Data is stored in the named volume `ledger_data` — rebuilding images does **not** lose data.

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+

### 1. Install dependencies

```bash
# Python (core library + API)
pip install -r apps/api/requirements.txt

# Node (frontend)
cd apps/web && npm install
```

### 2. Start the API

```bash
DB_PATH=data/ledger.db uvicorn apps.api.main:app --reload --port 8000
# Swagger UI → http://localhost:8000/docs
```

### 3. Start the Web (new terminal)

```bash
cd apps/web
API_URL=http://localhost:8000 npm run dev
# Frontend → http://localhost:3000
```

> `API_URL` is a **server-side** variable. Next.js rewrites `/api/*` → FastAPI, so the browser never needs a direct connection to port 8000 (no CORS issues).

### 4. Run example scripts

```bash
python examples/01_add_cash.py
python examples/02_add_trade.py
python examples/03_equity_curve.py
```

### 5. Run tests

```bash
python tests/test_ledger.py
python tests/test_new_features.py   # cash void + trade tax
```

---

## Project Structure

```
stock_ledger/
├── ledger/                  # Core Python library
│   ├── db.py                #   SQLite connection & schema init
│   ├── ledger.py            #   StockLedger class
│   └── equity.py            #   equity_curve(), print_curve(), plot_curve()
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── main.py
│   │   └── routers/         #   cash, trades, positions, equity, quotes,
│   │                        #   perf, rebalance, export_import, backup, demo …
│   └── web/                 # Next.js 14 frontend
│       └── src/
│           ├── app/         #   portfolio, cash, trades, positions,
│           │                #   quotes, lots, import, settings …
│           ├── components/  #   charts, forms, FAB, Nav, shadcn/ui
│           ├── hooks/       #   TanStack Query hooks & mutations
│           └── lib/         #   api.ts, types.ts, format.ts, utils.ts
├── examples/                # Standalone CLI demos
├── tests/                   # Unit tests (stdlib unittest)
├── docker-compose.yml
└── data/                    # SQLite DB (auto-created)
```

---

## API Endpoints

### Cash

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/cash` | Deposit or withdraw cash |
| `GET` | `/api/cash/balance` | Current cash balance (`?as_of=YYYY-MM-DD`) |
| `GET` | `/api/cash/tx` | Cash transaction history (`?start=&end=&include_void=`) |
| `PATCH` | `/api/cash/{id}/void` | Soft-delete a cash entry |

### Trades

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/trades` | Record a buy or sell (adjusts cash automatically) |
| `GET` | `/api/trades` | Trade history (`?symbol=&start=&end=&include_void=`) |
| `PATCH` | `/api/trades/{id}/void` | Soft-delete a trade |

### Positions & Equity

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/positions` | Holdings with avg cost, unrealized & realized P&L |
| `GET` | `/api/equity/snapshot` | Point-in-time: cash / market value / total equity |
| `GET` | `/api/equity/curve` | Equity curve records (`?start=&end=&freq=ME\|W\|D`) |

### Quotes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/quotes/manual` | Add a manual closing price |
| `GET` | `/api/quotes/last` | Latest price + source for a symbol |
| `GET` | `/api/quotes/todo` | Symbols missing or stale quotes (`?stale_days=2`) |

### Analytics

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/perf/summary` | CAGR, Sharpe, max drawdown (`?start=&end=`) |
| `GET` | `/api/risk/metrics` | VaR, volatility, beta (`?start=&end=`) |
| `GET` | `/api/rebalance/check` | Concentration & cash-level alerts |

### Import / Export / Backup

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/export/trades.csv` | Export trades as CSV |
| `GET` | `/api/export/cash.csv` | Export cash entries as CSV |
| `GET` | `/api/export/quotes.csv` | Export price quotes as CSV |
| `POST` | `/api/import/trades.csv` | Import trades (`?dry_run=true`) |
| `POST` | `/api/import/cash.csv` | Import cash entries (`?dry_run=true`) |
| `POST` | `/api/import/quotes.csv` | Import price quotes (`?dry_run=true`) |
| `GET` | `/api/backup/db` | Download the SQLite database file |
| `POST` | `/api/restore/db` | Upload and restore a database file |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/demo/seed` | Clear and seed with sample data |
| `GET` | `/api/health` | Health check |

---

## Frontend Pages

| Route | Description |
|-------|-------------|
| `/portfolio` | Dashboard: equity snapshot, charts, positions, P&L, rebalance alerts |
| `/cash` | Cash ledger with void support and date filtering |
| `/trades` | Trade history with void support and symbol/date filtering |
| `/positions` | Open positions: avg cost, unrealized/realized P&L, price source |
| `/quotes` | Manual price entry |
| `/lots` | Tax lot detail |
| `/import` | CSV upload (trades / cash / quotes) with dry-run preview |
| `/settings` | Export CSV, backup & restore database |

---

## Data Model

### Tables

| Table | Purpose |
|-------|---------|
| `cash_entries` | Manual deposits & withdrawals (`is_void` soft-delete) |
| `trades` | Buy/sell records; cash is adjusted automatically (`is_void`, `tax`) |
| `prices` | Closing prices for mark-to-market |

### Cash Flow Rules

| Action | Cash Effect |
|--------|------------|
| Buy | `cash -= qty × price + commission + tax` |
| Sell | `cash += qty × price − commission − tax` |

### Price Lookup Order

1. `prices` table (manual quotes via `POST /api/quotes/manual`)
2. Last trade price (`price_source: "trade_fallback"`)

---

## Environment Variables

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `DB_PATH` | API | `data/ledger.db` | SQLite file path |
| `API_URL` | Web | `http://localhost:8000` | FastAPI base URL (server-side proxy) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Core library | Python, SQLite (stdlib) |
| Backend | FastAPI, Uvicorn, Pandas |
| Frontend | Next.js 14, TypeScript, TanStack Query v5, Recharts, Tailwind CSS, shadcn/ui |
| Container | Docker, Docker Compose |
