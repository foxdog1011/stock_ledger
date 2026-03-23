# Stock Ledger

A full-stack personal portfolio tracker and investment research platform — built from a raw SQLite core library up through a REST API, an interactive Next.js dashboard, and an AI portfolio analyst powered by Claude.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)
![Claude](https://img.shields.io/badge/Claude-claude--opus--4--6-orange)
![Tests](https://img.shields.io/badge/tests-336-brightgreen)
![Docker](https://img.shields.io/badge/Docker-compose-blue)
![AWS EC2](https://img.shields.io/badge/AWS-EC2%20t2.micro-orange)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-blue)
![Terraform](https://img.shields.io/badge/IaC-Terraform-purple)

---

## Highlights

- **AI portfolio analyst (J.A.R.V.I.S.)** — Claude claude-opus-4-6 with 7 tool-use functions; agentic loop autonomously queries positions, risk metrics, P&L, and lot details before answering in natural language; SSE streaming renders token-by-token in a floating HUD panel
- **Market anomaly detection** — PCA-based linear autoencoder on 6-feature multivariate time-series (price, volume, volatility, Z-score, Bollinger Band %B); data-driven threshold (μ + 2.5σ reconstruction error) replaces fixed contamination ratios; batch-scans all active positions simultaneously; analogous to multivariate SPC in manufacturing
- **End-to-end ownership** — pure-Python core library → 40+ REST endpoints → TypeScript frontend, zero third-party portfolio SDK
- **Domain-Driven Design** — separate `domain/` layer decouples business logic (risk, execution, overview) from API routing and persistence
- **Quantitative analytics** — Sharpe ratio, max drawdown, VaR, volatility; benchmark comparison with tracking error, information ratio, and correlation vs. 0050 / SPY / QQQ / TAIEX
- **Investment research pipeline** — Universe (company DB) → Watchlist (investment thesis) → Catalyst (event tracking) → Daily Digest (auto-generated report)
- **Multi-provider quote engine** — pluggable `PriceProvider` ABC with TWSE, FinMind, and Yahoo Finance backends; APScheduler cron at 18:00 TST; background refresh fires on every trade
- **Tax-aware P&L** — commission and transaction tax flow into cost basis; lot-level FIFO / LIFO / HIFO breakdown; loss-offsetting simulation for tax-loss harvesting
- **336 unit tests** across 13 test files covering domain services, API integration, and CSV import validation

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Next.js 14  ·  TypeScript  ·  TanStack Query v5  ·  shadcn   │
│  /overview /portfolio /positions /lots /universe /catalyst     │
│  /digest /offsetting /anomaly /alerts /settings  …            │
│  /anomaly /alerts /allocation /chip /revenue /rolling         │
│  /screener  …                                                  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  J.A.R.V.I.S. floating panel  (Ctrl+J, any page)        │  │
│  │  SSE streaming · tool-call badges · page-context aware   │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────┬────────────────────────────────────┘
                           │  HTTP  (server-side proxy, no CORS)
┌──────────────────────────▼────────────────────────────────────┐
│  FastAPI  ·  40+ endpoints  ·  21 routers                      │
│  APScheduler  (daily quote refresh @ 18:00 Asia/Taipei)        │
│  BackgroundTasks  (auto-refresh on every trade POST)           │
│                                                                │
│  POST /api/chat/stream ──► Anthropic Claude API                │
│    agentic loop: tool_use → execute → tool_result → stream     │
│                                                                │
│  GET /api/anomaly/batch ──► analysis/ (PCA Autoencoder)        │
│    6-feature time-series → reconstruction error → anomalies    │
│                                                                │
│  GET /api/chart/{symbol} ──► yfinance (MA/RSI/KD)             │
│    fetches directly; supports US + Taiwan (.TW/.TWO)           │
└──────┬──────────────────┬──────────────────┬──────────────────┘
       │                  │                  │
  domain/ layer      ledger/ library    providers/
  (DDD services)     (pure Python core)  TWSE · FinMind · Yahoo
       │                  │              yfinance (chart + anomaly)
       └──────────────────┴──── SQLite  (Docker named volume)
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Agentic loop in `POST /api/chat/stream` | Model selects and sequences tools autonomously; frontend only streams the result |
| SSE over WebSocket for chat | Unidirectional server-push is sufficient; simpler than full duplex; no connection keep-alive overhead |
| Pure Python `ledger/` library with zero web dependencies | Independently testable; usable as CLI or imported without running the API |
| `domain/` layer separate from `apps/api/routers/` | Routers handle HTTP concerns only; business logic is framework-agnostic |
| PCA reconstruction error over Isolation Forest contamination | Data-driven threshold adapts to each asset's own baseline; no need to specify expected anomaly ratio |
| Static `/anomaly/batch` route defined before `/{symbol}` | Prevents FastAPI path parameter capture; required explicit route ordering |
| Pluggable `PriceProvider` ABC | Swap or add data sources without touching the scheduler or refresh service |
| Next.js server-side `API_URL` proxy | Eliminates CORS; frontend never needs direct access to the API port |

---

## J.A.R.V.I.S. — AI Portfolio Analyst

A floating assistant panel (bottom-left button, or `Ctrl+J`) available on every page. Powered by Claude claude-opus-4-6 with tool use.

**How it works:**

```
User question
  └─► POST /api/chat/stream
        └─► Claude decides which tools to call
              ├─► get_portfolio_snapshot   →  ledger.equity_snapshot()
              ├─► get_positions            →  ledger.position_pnl()
              ├─► get_risk_metrics         →  daily equity series → Sharpe / vol / win rate
              ├─► get_perf_summary         →  P&L ex-cashflow / realized / unrealized / fees
              ├─► get_lots(symbol)         →  ledger.lots_by_method()
              ├─► get_cash_balance         →  ledger.cash_balance()
              └─► get_recent_trades        →  ledger.trade_history()
        └─► Tool results fed back to model
        └─► Final answer streamed token-by-token via SSE
```

The panel is **page-context aware** — it tells Claude which page the user is viewing so responses are more relevant. Tool calls are surfaced as cyan badges above each response.

**Setup:**

```bash
# Requires an Anthropic API key
ANTHROPIC_API_KEY=sk-ant-... DB_PATH=data/ledger.db uvicorn apps.api.main:app --port 8000
```

**Example queries:**
- *"How is my portfolio performing this year?"*
- *"Which of my positions is most underwater?"*
- *"What is my Sharpe ratio and how does it compare to a 60/40 portfolio?"*
- *"Show me the lot breakdown for AAPL and explain my average cost"*

---

## Market Anomaly Detection

`/anomaly` — scans for statistically unusual price and volume behavior across the portfolio. Framed around the **Informed Trading Hypothesis**: significant market events often leave traces in price and volume before any public announcement.

**How it works:**

```
analysis/anomaly_detector.py
  ├─► Z-score detector (rolling 20-day, σ=2.5)
  │     Detects sudden single-variable spikes (price or volume)
  │
  └─► PCA Autoencoder (sklearn, n_components=2)
        6 features: [close, volume_ratio, price_change_pct,
                     volatility_5, zscore_20, bb_pct]
        Compress → reconstruct → MSE per point
        Threshold: mean(RE) + 2.5 × std(RE)  ← fully data-driven
        Flags points where reconstruction error exceeds threshold
```

**Batch scan** (`GET /api/anomaly/batch`) queries all active positions at once and returns a compact summary — analogous to monitoring all manufacturing stations simultaneously.

**Volume enrichment** — when a symbol has no volume data in the local DB, the detector automatically fetches volume from Yahoo Finance via `yfinance` and falls back silently if unavailable.

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

Seed realistic demo data (5 positions, 13 months of history) from the dashboard FAB or:

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

`/portfolio` — real-time snapshot of cash, market value, total equity, unrealized and realized P&L. Equity curve supports D / W / ME frequency with a dual-axis chart (equity + cumulative return %). Daily P&L bar chart with weekday/all-days toggle.

`GET /api/perf/summary` → P&L ex-cashflow, realized P&L, unrealized P&L, fees
`GET /api/risk/metrics` → Sharpe ratio, annualized volatility, best/worst day, win rate

### Benchmark Comparison

Bootstrap historical prices from Yahoo Finance (no API key) for 0050, TAIEX, SPY, QQQ, or any ticker. The compare endpoint aligns the portfolio equity curve with the benchmark and computes:

- Excess return (cumulative)
- Tracking error (annualized)
- Pearson correlation
- Information ratio

### Market Anomaly Detection

`/anomaly` — two panels:

1. **Batch scan** — auto-detects anomalies across all active positions; shows per-symbol anomaly count, severity badge, and latest signal description
2. **Single symbol query** — enter any ticker; returns unified table of Z-score and autoencoder anomalies sorted by date, with close price, daily return %, severity level, and plain-language reason

Integrates with the catalyst calendar: anomaly signals provide early context; catalyst events explain the fundamental reason.

### Investment Research Pipeline

| Stage | Endpoint group | Purpose |
|---|---|---|
| Universe | `/api/universe` | Company master: sector, industry, business model, peer relationships, thesis notes |
| Watchlist | `/api/watchlist` | Curated monitoring lists; coverage check ensures 3× open positions; accessible via Universe page tab |
| Catalyst | `/api/catalyst` | Event log (earnings, macro, sector) with Plan A/B/C/D scenarios and price targets |
| Digest | `/api/digest` | Auto-generated daily report: P&L, top movers, upcoming catalysts, rebalance alerts |

### Execution Tools

- **Cost impact analysis** — before adding to a position, see exactly how the new buy shifts average cost and unrealized P&L across all open lots
- **Lot viewer** — FIFO / LIFO / HIFO lot breakdown with per-lot unrealized % and underwater % visualized as a bubble chart
- **Loss-offsetting simulator** — list losing positions, check available realized-gain inventory, simulate crystallizing a loss to offset gains for tax purposes

### Quote Engine

| Provider | Coverage | Auth |
|---|---|---|
| `TWSeProvider` | TWSE listed + OTC (Taiwan) | None |
| `FinMindProvider` | Taiwan stock history | `FINMIND_TOKEN` |
| `YahooProvider` | US, HK, global | None |
| `SmartProvider` | Auto-routes by ticker pattern | — |

Refresh triggers:
1. **Daily cron** — 18:00 Asia/Taipei via APScheduler
2. **On trade** — `POST /api/trades` fires a background refresh (`skip_if_fresh=True`)
3. **On demand** — `POST /api/quotes/refresh`

All runs logged to `quote_refresh_log` with timestamp, provider, inserted/skipped/error counts, and trigger type (`manual` | `schedule` | `trade`).

### Data Operations

| Feature | Detail |
|---|---|
| Soft delete | `is_void` flag on `cash_entries` and `trades`; history is never destroyed |
| CSV import | `dry_run=true` previews insert/skip/error counts before committing |
| CSV export | Trades, cash |
| DB backup / restore | Download and re-upload the raw SQLite file from `/settings` |

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
| `GET` | `/api/perf/summary` | P&L ex-cashflow, realized / unrealized P&L, fees |
| `GET` | `/api/risk/metrics` | Sharpe, volatility, best/worst day, win rate |
| `GET` | `/api/rebalance/check` | Concentration and cash-level alerts |

### Anomaly Detection

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/anomaly/batch` | Scan all active positions; returns per-symbol anomaly summary |
| `GET` | `/api/anomaly/{symbol}` | Z-score + PCA autoencoder anomalies for a single ticker (`?days=&ae_threshold=`) |

### AI Chat

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat/stream` | SSE stream: agentic tool loop then streamed text response |

### Benchmark

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/benchmark/series` | Benchmark price series + cumulative return |
| `GET` | `/api/benchmark/compare` | Portfolio vs. benchmark with excess return, tracking error, correlation, IR |
| `POST` | `/api/benchmark/bootstrap` | Fetch historical data from Yahoo Finance into local DB |
| `GET` | `/api/benchmark/bootstrap/status` | Last bootstrap run log |

### Execution

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/execution/offset/losing` | All open losing positions |
| `GET` | `/api/execution/offset/profit-inventory` | Realized gains available to offset |
| `GET` | `/api/execution/offset/simulate/{symbol}` | Simulate crystallizing a loss |

### Quotes (Auto-refresh only)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/quotes/refresh` | Trigger a provider refresh |
| `GET` | `/api/quotes/refresh/status` | Last refresh run log |
| `GET` | `/api/quotes/provider` | Configured provider info |

### Universe & Watchlist

| Method | Path | Description |
|---|---|---|
| `POST/GET` | `/api/universe/companies` | Company master CRUD |
| `GET` | `/api/universe/companies/{symbol}` | Company detail + thesis + relationships |
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
| `GET` | `/api/export/{trades\|cash}.csv` | Download as CSV |
| `POST` | `/api/import/{trades\|cash}.csv` | Upload CSV (`?dry_run=true`) |
| `GET` | `/api/backup/db` | Download SQLite file |
| `POST` | `/api/restore/db` | Restore from uploaded file |

---

## Frontend Pages

| Route | Description |
|---|---|
| `/overview` | Unified dashboard: snapshot, risk summary, watchlist coverage, catalyst feed |
| `/portfolio` | Equity curve, daily P&L chart, benchmark comparison, asset allocation donut |
| `/positions` | Holdings with cost impact analysis and expandable lot details |
| `/lots/[symbol]` | Lot-level breakdown + bubble chart (unrealized % vs. underwater %) |
| `/anomaly` | Market anomaly detection: batch portfolio scan + single symbol Z-score/autoencoder query |
| `/alerts` | Price alert management |
| `/allocation` | Portfolio allocation analysis and targets |
| `/chip` | Chip distribution (籌碼) analysis |
| `/revenue` | Revenue trend analysis |
| `/rolling` | Rolling performance metrics |
| `/screener` | Stock screener |
| `/universe` | Company research database + watchlist (tabbed: 股票池 / 觀察清單) |
| `/catalyst` | Event log with Plan A/B/C/D scenario planner |
| `/digest` | Daily portfolio report history |
| `/offsetting` | Tax-loss harvesting simulator |
| `/trades` | Trade history with void support |
| `/cash` | Cash ledger with void support |
| `/import` | CSV upload with dry-run preview |
| `/settings` | Provider config, export, backup / restore, benchmark bootstrap |

**Global:** J.A.R.V.I.S. floating panel (`Ctrl+J`) accessible from any route.

---

## Project Structure

```
stock_ledger/
├── analysis/                  # Quantitative analysis modules
│   ├── anomaly_detector.py    #   PCA autoencoder + Z-score anomaly detection
│   └── time_series.py         #   Rolling statistics helpers
├── domain/                    # Domain layer (DDD) — framework-agnostic
│   ├── overview/              #   Dashboard aggregation service
│   ├── execution/             #   Loss-offsetting simulation
│   ├── portfolio/             #   Portfolio-level calculations
│   ├── risk/                  #   Risk metric computation
│   ├── universe/              #   Company research domain
│   └── watchlist/             #   Watchlist and thesis tracking
├── ledger/                    # Core Python library (no web deps)
│   ├── db.py                  #   SQLite connection + schema + migrations
│   ├── ledger.py              #   StockLedger class
│   └── equity.py              #   equity_curve(), print_curve(), plot_curve()
├── apps/
│   ├── api/                   # FastAPI application
│   │   ├── providers/         #   PriceProvider ABC + TWSE, FinMind, Yahoo, Auto
│   │   ├── services/          #   QuotesRefreshService
│   │   ├── routers/
│   │   │   ├── anomaly.py     #   GET /api/anomaly/batch, /api/anomaly/{symbol}
│   │   │   ├── chat.py        #   POST /api/chat/stream — Claude agentic loop + SSE
│   │   │   └── …              #   20 other route modules
│   │   ├── config.py          #   Environment config
│   │   ├── deps.py            #   FastAPI dependencies
│   │   └── main.py            #   App factory + APScheduler lifespan
│   └── web/                   # Next.js 14 frontend
│       └── src/
│           ├── app/           #   20 page routes
│           ├── components/
│           │   ├── JarvisPanel.tsx   # AI chat HUD (floating, any page)
│           │   ├── Fab.tsx           # Speed-dial for data entry
│           │   └── …
│           ├── hooks/         #   TanStack Query hooks + mutations
│           └── lib/           #   api.ts, types.ts, format.ts
├── tests/                     # 336 tests across 13 files
├── docker-compose.yml
└── data/                      # SQLite DB (auto-created)
```

---

## CI/CD Pipeline

Every `git push origin main` triggers the full automation:

```
git push
  └── GitHub Actions CI
        ├── pytest          (336 unit tests + smoke test)
        ├── ESLint          (TypeScript/React lint)
        └── tsc --noEmit    (TypeScript type check)
              ↓ all pass
        GitHub Actions CD
          ├── docker build × 3  (api / mcp / web)
          ├── docker push → AWS ECR  (tagged :$SHA + :latest)
          └── SSH → EC2
                ├── docker compose pull
                ├── docker compose up -d --remove-orphans
                └── docker image prune -f
```

Zero-downtime rolling update on every push; no manual server access required after initial setup.

---

## AWS Infrastructure (Terraform)

Provisioned with Terraform (`aws/terraform/`), all resources in `ap-northeast-1` (Tokyo):

| Resource | Detail |
|---|---|
| **EC2 t2.micro** | Amazon Linux 2023, Elastic IP (ap-northeast-1) |
| **ECR × 3** | `stock-ledger-api` / `mcp` / `web` — lifecycle policy keeps last 5 images |
| **VPC + Subnet** | Single public subnet, Internet Gateway |
| **Security Group** | Ports 80 / 443 / 22 |
| **IAM Role** | EC2 instance profile with ECR pull + CloudWatch Logs permissions |
| **CloudWatch** | Log group `/ec2/stock-ledger`, 14-day retention |
| **Nginx** | Reverse proxy: `/api/*` → FastAPI :8000, `/*` → Next.js :3001 |

```bash
cd aws/terraform
terraform init
terraform apply   # provisions all resources in ~2 minutes
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI | Anthropic Claude claude-opus-4-6 (tool use, SSE streaming) |
| Anomaly Detection | scikit-learn PCA (linear autoencoder), Z-score (rolling window) |
| Core library | Python 3.11, SQLite (stdlib only) |
| Backend | FastAPI, Uvicorn, Pandas, APScheduler, yfinance |
| Frontend | Next.js 14, TypeScript, TanStack Query v5, Recharts, Tailwind CSS, shadcn/ui |
| Testing | Python `unittest` (336 tests, 13 files) |
| Container | Docker, Docker Compose |
| Infrastructure | AWS EC2, ECR, VPC, IAM, CloudWatch — provisioned via Terraform |
| CI/CD | GitHub Actions — pytest + ESLint + tsc → build ECR images → SSH deploy |

---

## MCP Server (Model Context Protocol)

Stock Ledger exposes a fully-typed MCP server so any MCP-compatible AI client (Claude Desktop, custom agents) can query and manage the portfolio directly via tool calls — no REST API knowledge needed.

### Setup (Claude Desktop)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "stock-ledger": {
      "command": "python",
      "args": ["/path/to/stock_ledger/apps/mcp/server.py"],
      "env": {
        "DB_PATH": "/path/to/stock_ledger/data/ledger.db"
      }
    }
  }
}
```

### Available Tools

| Tool | Description |
|---|---|
| `get_portfolio_snapshot` | High-level snapshot: total equity, cash, market value, position count |
| `get_positions` | All positions with cost basis, unrealized/realized P&L, last price |
| `get_cash_balance` | Current or point-in-time cash balance |
| `get_recent_trades` | Recent trade history with symbol, qty, price, date |
| `get_cash_transactions` | Cash ledger entries: deposits, withdrawals, dividends |
| `get_perf_summary` | Portfolio performance over a date range: return, Sharpe, drawdown |
| `get_risk_metrics` | Risk metrics: VaR, volatility, beta, concentration |
| `detect_anomalies` | PCA + rolling Z-score anomaly detection for any symbol |
| `get_catalyst_events` | Upcoming earnings, dividends, and conference events |
| `get_universe_companies` | All companies in the investment universe |
| `get_watchlists` | All watchlists and their constituent symbols |
| `get_rebalance_check` | Check if rebalancing is needed based on concentration limits |
| `get_lots` | Lot-level position detail (FIFO / LIFO / HIFO cost methods) |
| `get_price_alerts` | List active stop-loss and target-price alerts |
| `add_price_alert` | Create a new price alert for a symbol |
| `delete_price_alert` | Remove a price alert by ID |
| `add_trade` | Record a new buy/sell trade |
| `add_cash` | Record a cash deposit or withdrawal |

### Example Prompts (via Claude Desktop)

```
"What's my portfolio worth today?"
→ calls get_portfolio_snapshot

"Show me all losing positions"
→ calls get_positions, filters unrealized_pnl < 0

"Detect any anomalies in 2330 this week"
→ calls detect_anomalies(symbol="2330", lookback_days=7)

"Am I overweight in any single stock?"
→ calls get_rebalance_check
```

---

## Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `DB_PATH` | API | `data/ledger.db` | SQLite file path |
| `ANTHROPIC_API_KEY` | API | _(empty)_ | Required for J.A.R.V.I.S. chat feature |
| `API_URL` | Web | `http://localhost:8000` | FastAPI base URL (server-side only) |
| `QUOTE_PROVIDER` | API | `auto` | `twse` \| `finmind` \| `yahoo` \| `auto` |
| `FINMIND_TOKEN` | API | _(empty)_ | Required only for FinMind provider |
| `AUTO_REFRESH_QUOTES_ON_TRADE` | API | `1` | Set to `0` to disable background refresh on trade |
| `TZ` | API | `Asia/Taipei` | Scheduler timezone |
