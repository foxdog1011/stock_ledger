# Stock Ledger

Taiwan-focused portfolio tracking & investment research platform with AI assistant (J.A.R.V.I.S.).

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLite (WAL mode), APScheduler
- **Frontend**: Next.js 14, React 18, TypeScript, Tailwind CSS, shadcn/ui, Recharts, TanStack Query v5
- **AI**: Claude Opus 4.6 (via Anthropic SDK), OpenAI gpt-4o-mini (script generation)
- **Video**: matplotlib slides, Edge-TTS (zh-TW-HsiaoChenNeural), ffmpeg, YouTube Data API v3
- **Data**: yfinance, FinMind, TWSE, FRED
- **Infra**: Docker Compose (3 services), AWS EC2 (Terraform), n8n (workflow automation)
- **Testing**: pytest (346 tests, 93% coverage)

## Architecture

```
stock_ledger/
  ledger/          # Core library — pure Python, no web deps
    ledger.py      # StockLedger class (add_cash, add_trade, add_price, equity_snapshot)
    db.py          # SQLite connection & schema init
    equity.py      # Equity/position calculations
  domain/          # DDD business logic (14 modules)
    anomaly/       # PCA-based multivariate anomaly detection
    calendar/      # Content calendar & planning
    catalyst/      # Event catalyst tracking
    execution/     # Trade execution & tax-loss offsetting (FIFO/LIFO/HIFO)
    financials/    # Financial data models
    overview/      # Portfolio summary service
    portfolio/     # Lot tracking & P&L
    rating/        # Stock rating system
    risk/          # Sharpe, VaR, max drawdown, volatility
    scenario/      # What-if simulation
    trump_put/     # S&P/10Y/VIX composite volatility tracker
    universe/      # Company universe DB (1,735 TWSE+OTC), supply chain mapping
    watchlist/     # Investment thesis tracking
  apps/
    api/           # FastAPI backend (port 8000), 40+ routers
    mcp/           # MCP server (port 8001) — exposes portfolio tools for Claude
    web/           # Next.js frontend (port 3001), 20+ pages
  scripts/         # Automation: n8n workflows, YouTube auth, Discord briefing
  aws/             # Terraform IaC + ECS task definitions
  tests/           # pytest suite
```

## Services (Docker Compose)

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| api | stock-ledger-api | 8000 | FastAPI backend |
| mcp | stock-ledger-mcp | 8001 | MCP tools for Claude |
| web | stock-ledger-web | 3001 | Next.js dashboard |

Additional (external):
- **n8n** (`ielts-n8n` container, port 5800) — workflow automation, YouTube video scheduling
- **Local API** (port 8003) — local uvicorn for n8n to call via `host.docker.internal:8003`

## Common Commands

```bash
# Run tests
cd stock_ledger && python -m pytest tests/ -v

# Start Docker services
docker compose up -d --build

# Start local API for n8n
cd stock_ledger && python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8003

# Type check frontend
cd apps/web && npx tsc --noEmit

# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## Environment Variables (.env)

| Variable | Purpose |
|----------|---------|
| OPENAI_API_KEY | Script generation (gpt-4o-mini) |
| DISCORD_BOT_TOKEN | Daily briefing bot |
| DISCORD_CHANNEL_ID | Target Discord channel |
| FINMIND_TOKEN | Taiwan stock data provider |
| JARVIS_KEY | AI assistant auth |
| YOUTUBE_CLIENT_ID | YouTube upload OAuth |
| YOUTUBE_CLIENT_SECRET | YouTube upload OAuth |
| YOUTUBE_REFRESH_TOKEN | YouTube upload OAuth |
| FRED_API_KEY | Federal Reserve economic data |

## n8n Workflows

| ID | Name | Schedule (Asia/Taipei) |
|----|------|----------------------|
| 1001 | JARVIS YouTube v3 全排程 | 17:00 盤後速報, 19:00 晚間/族群/週報, 週末 09:00/19:00 |
| 1002 | Health Monitor | Every hour |
| 1003 | 籌碼異常偵測 | 16:00 Mon-Fri |
| 1004 | 盤前美股 Shorts | 08:00 Mon-Sat |

All n8n workflows call `http://host.docker.internal:8003` (local API on port 8003).

## API Patterns

- All endpoints under `/api/` prefix
- Pydantic models for request/response validation
- Rate limiting via slowapi (120/min)
- DEMO_MODE=1 blocks writes (except /api/demo/seed)
- APScheduler runs daily: quote refresh 18:00, Discord notification 18:30, digest 20:00

## Database

- SQLite with WAL mode (concurrent reads/writes across workers)
- Schema auto-initialized on startup via `ledger/db.py`
- Domain tables initialized in `apps/api/main.py` lifespan
- Docker volume `ledger_data` at `/data/ledger.db`

## Frontend Conventions

- Pages in `apps/web/src/app/` (Next.js App Router)
- Components in `apps/web/src/components/` (shadcn/ui based)
- API calls via TanStack Query hooks
- J.A.R.V.I.S. floating panel: Ctrl+J
- SSE streaming for AI chat responses
- Zod + react-hook-form for form validation

## Video Generation Pipeline

1. **Pick stock**: `/api/video-gen/pick-stock` — selects stock by chip anomaly
2. **Generate**: `/api/video-gen/generate` — matplotlib slides + OpenAI script + Edge-TTS + ffmpeg
3. **Upload**: `/api/video-gen/upload-youtube` — YouTube Data API v3

Shorts (pre-market): `scripts/premarket_shorts.py` — standalone pipeline for US market data.

## Deployment

- **Local**: `docker compose up -d --build`
- **AWS**: Terraform in `aws/terraform/`, EC2 t2.micro ap-northeast-1
- **CI/CD**: GitHub Actions — pytest + tsc on push, CD pushes to ECR
