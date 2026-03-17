"""FastAPI application entry point."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make the project root importable so `ledger` package is found
# regardless of where uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import deps
from .tz import TZ
from .routers import (
    cash, demo, equity, positions, quotes, trades, daily, lots,
    todo, perf, rebalance, export_import, backup, benchmark, risk, execution,
    universe, watchlist, catalyst, overview,
)
from .routers import quotes_refresh, digest as digest_router

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def _run_scheduled_refresh() -> None:
    """Daily 18:00 Asia/Taipei price refresh job."""
    try:
        ledger = deps.get_ledger()
        from .routers.quotes_refresh import do_refresh
        result = do_refresh(ledger=ledger, trigger="schedule")
        logger.info(
            "Scheduled refresh: provider=%s as_of=%s inserted=%d errors=%d",
            result.provider, result.as_of, result.inserted, len(result.errors),
        )
    except Exception:
        logger.exception("Scheduled refresh failed")


async def _run_scheduled_digest() -> None:
    """Daily 20:00 Asia/Taipei digest generation job."""
    try:
        import datetime
        ledger = deps.get_ledger()
        date = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
        from .routers.digest import generate_and_save
        row = generate_and_save(ledger=ledger, date=date, overwrite=True)
        logger.info("Scheduled digest generated: date=%s total_equity=%s", date, row.get("total_equity"))
    except Exception:
        logger.exception("Scheduled digest generation failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup."""
    deps.init_ledger()

    # Ensure universe tables exist
    from domain.universe.repository import init_universe_tables
    from .config import DB_PATH
    init_universe_tables(DB_PATH)

    # Ensure watchlist tables exist
    from domain.watchlist.repository import init_watchlist_tables
    init_watchlist_tables(DB_PATH)

    # Ensure catalyst + scenario tables exist
    from domain.catalyst.repository import init_catalyst_tables
    from domain.scenario.repository import init_scenario_tables
    init_catalyst_tables(DB_PATH)
    init_scenario_tables(DB_PATH)

    # Ensure refresh log table exists
    from .routers.quotes_refresh import _ensure_log_table
    _ensure_log_table()

    # Ensure digest table exists
    from .routers.digest import ensure_digest_table
    ensure_digest_table()

    # APScheduler: daily price refresh at 18:00 Asia/Taipei
    _scheduler.add_job(
        _run_scheduled_refresh,
        CronTrigger(hour=18, minute=0, timezone=TZ),
        id="daily_refresh",
        replace_existing=True,
    )
    # APScheduler: daily digest generation at 20:00 Asia/Taipei
    _scheduler.add_job(
        _run_scheduled_digest,
        CronTrigger(hour=20, minute=0, timezone=TZ),
        id="daily_digest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler started (refresh 18:00, digest 20:00 Asia/Taipei)")

    yield

    _scheduler.shutdown(wait=False)


app = FastAPI(
    title="Stock Ledger API",
    version="1.0.0",
    description=(
        "SQLite-backed portfolio ledger.  "
        "Point `DB_PATH` env var at a mounted volume for persistence."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
PREFIX = "/api"

app.include_router(cash.router,           prefix=PREFIX, tags=["cash"])
app.include_router(trades.router,         prefix=PREFIX, tags=["trades"])
app.include_router(positions.router,      prefix=PREFIX, tags=["positions"])
app.include_router(equity.router,         prefix=PREFIX, tags=["equity"])
app.include_router(quotes.router,         prefix=PREFIX, tags=["quotes"])
app.include_router(demo.router,           prefix=PREFIX, tags=["demo"])
app.include_router(daily.router,          prefix=PREFIX, tags=["equity"])
app.include_router(lots.router,           prefix=PREFIX, tags=["lots"])
app.include_router(todo.router,           prefix=PREFIX, tags=["quotes"])
app.include_router(perf.router,           prefix=PREFIX, tags=["perf"])
app.include_router(rebalance.router,      prefix=PREFIX, tags=["rebalance"])
app.include_router(export_import.router,  prefix=PREFIX, tags=["import-export"])
app.include_router(backup.router,         prefix=PREFIX, tags=["system"])
app.include_router(quotes_refresh.router, prefix=PREFIX, tags=["quotes"])
app.include_router(digest_router.router,  prefix=PREFIX, tags=["digest"])
app.include_router(benchmark.router,      prefix=PREFIX)
app.include_router(risk.router,           prefix=PREFIX, tags=["risk"])
app.include_router(execution.router,      prefix=PREFIX, tags=["execution"])
app.include_router(universe.router,       prefix=PREFIX, tags=["universe"])
app.include_router(watchlist.router,      prefix=PREFIX, tags=["watchlist"])
app.include_router(catalyst.router,      prefix=PREFIX, tags=["catalyst"])
app.include_router(overview.router,      prefix=PREFIX, tags=["overview"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
def health():
    """Liveness probe."""
    return {"status": "ok"}
