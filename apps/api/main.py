"""FastAPI application entry point."""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make the project root importable so `ledger` package is found
# regardless of where uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from . import deps
from .tz import TZ
from .routers import (
    cash, demo, equity, positions, trades, daily, lots,
    todo, perf, rebalance, export_import, backup, benchmark, risk, execution,
    universe, watchlist, catalyst, overview, chat, alerts, chip, rolling,
    chart, revenue, allocation, screener, anomaly, research, deep_dive,
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


async def _run_daily_discord_notification() -> None:
    """Daily 18:30 Asia/Taipei — post alerts + chip + sector check to Discord."""
    import json
    import os
    import urllib.request
    import urllib.parse
    import datetime

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.getenv("DISCORD_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        logger.warning("DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID not set — skipping notification")
        return

    try:
        ledger = deps.get_ledger()
        today = datetime.datetime.now(TZ).strftime("%Y-%m-%d")

        # 1. Check price alerts
        from .routers.alerts import check_alerts as _check_alerts_fn, _get_db_path, _ensure_table
        db_path = _get_db_path()
        _ensure_table(db_path)
        import sqlite3
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            active_alerts = con.execute("SELECT * FROM price_alerts WHERE triggered=0").fetchall()

        triggered_alerts = []
        pending_alerts = []
        for alert in active_alerts:
            sym = alert["symbol"]
            price_info = ledger.last_price_with_source(symbol=sym, as_of=today)
            current = price_info.get("price")
            if current is None:
                continue
            fired = (
                (alert["alert_type"] == "stop_loss" and current <= alert["price"]) or
                (alert["alert_type"] == "target" and current >= alert["price"])
            )
            if fired:
                with sqlite3.connect(db_path) as con:
                    con.execute("UPDATE price_alerts SET triggered=1, triggered_at=? WHERE id=?",
                                (today, alert["id"]))
                triggered_alerts.append(f"🔔 **{sym}** {alert['alert_type'].upper()} @ {alert['price']} | 現價 {current}")
            else:
                gap = round((current - alert["price"]) / alert["price"] * 100, 1)
                pending_alerts.append(f"  {sym} {alert['alert_type']} {alert['price']} | 現價 {current} ({gap:+.1f}%)")

        # 2. Sector check
        from .routers.rolling import sector_check as _sector_check_fn
        snap = ledger.equity_snapshot(as_of=today)
        positions = snap.get("positions", {})
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            companies = {r["symbol"]: r for r in con.execute(
                "SELECT symbol, sector FROM company_master").fetchall()}

        sector_map: dict = {}
        total_mv = sum((pos.get("market_value") or 0) for pos in positions.values())
        for sym, pos in positions.items():
            mv = pos.get("market_value") or 0
            sector = companies.get(sym, {}).get("sector") or "未分類"
            if sector not in sector_map:
                sector_map[sector] = 0.0
            sector_map[sector] += mv

        sector_lines = []
        sector_alerts = []
        for sec, mv in sorted(sector_map.items(), key=lambda x: -x[1]):
            pct = round(mv / total_mv * 100, 1) if total_mv > 0 else 0
            sector_lines.append(f"  {sec} {pct}%")
            if pct > 50:
                sector_alerts.append(f"⚠️ {sec} 占 {pct}% 超過 50%")

        # Build message
        lines = [f"📊 **每日報告 {today}**\n"]

        if triggered_alerts:
            lines.append("**🚨 觸發警示：**")
            lines.extend(triggered_alerts)
        else:
            lines.append("✅ 無觸發警示")

        if pending_alerts:
            lines.append("\n**監控中：**")
            lines.extend(pending_alerts)

        lines.append("\n**產業分布：**")
        lines.extend(sector_lines)
        if sector_alerts:
            lines.extend(sector_alerts)

        message = "\n".join(lines)

        # Post to Discord
        payload = json.dumps({"content": message}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=payload,
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Daily Discord notification sent: status=%d", resp.status)

    except Exception:
        logger.exception("Daily Discord notification failed")


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
    # APScheduler: daily Discord notification at 18:30 Asia/Taipei
    _scheduler.add_job(
        _run_daily_discord_notification,
        CronTrigger(hour=18, minute=30, timezone=TZ),
        id="daily_discord_notification",
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


DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

# Endpoints allowed to write even in DEMO_MODE (seed is useful for demos)
_DEMO_WRITE_ALLOWLIST: set[str] = {"/api/demo/seed"}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    """Block all mutating requests when DEMO_MODE=1."""

    async def dispatch(self, request: Request, call_next):
        if DEMO_MODE and request.method in _WRITE_METHODS:
            if request.url.path not in _DEMO_WRITE_ALLOWLIST:
                return JSONResponse(
                    {"detail": "Demo 模式：僅開放讀取，不允許修改資料。"},
                    status_code=403,
                )
        return await call_next(request)


limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(
    title="Stock Ledger API",
    version="1.0.0",
    description=(
        "SQLite-backed portfolio ledger.  "
        "Point `DB_PATH` env var at a mounted volume for persistence."
    ),
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if DEMO_MODE:
    app.add_middleware(DemoReadOnlyMiddleware)
    logger.info("DEMO_MODE enabled — write operations are blocked")

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
app.include_router(chat.router,          prefix=PREFIX, tags=["chat"])
app.include_router(alerts.router,        prefix=PREFIX, tags=["alerts"])
app.include_router(chip.router,          prefix=PREFIX, tags=["chip"])
app.include_router(rolling.router,       prefix=PREFIX, tags=["rolling"])
app.include_router(chart.router,         prefix=PREFIX, tags=["chart"])
app.include_router(revenue.router,       prefix=PREFIX, tags=["revenue"])
app.include_router(allocation.router,    prefix=PREFIX, tags=["allocation"])
app.include_router(screener.router,      prefix=PREFIX, tags=["screener"])
app.include_router(anomaly.router,       prefix=PREFIX, tags=["anomaly"])
app.include_router(research.router,      prefix="/api/research", tags=["research"])
app.include_router(deep_dive.router,     prefix=PREFIX, tags=["deep-dive"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
def health():
    """Liveness probe."""
    return {"status": "ok"}
