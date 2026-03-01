"""FastAPI application entry point."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make the project root importable so `ledger` package is found
# regardless of where uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import deps
from .routers import (
    cash, demo, equity, positions, quotes, trades, daily, lots,
    todo, perf, rebalance, export_import, backup,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup."""
    deps.init_ledger()
    yield
    # Nothing to clean up (SQLite connections are per-request).


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

app.include_router(cash.router,      prefix=PREFIX, tags=["cash"])
app.include_router(trades.router,    prefix=PREFIX, tags=["trades"])
app.include_router(positions.router, prefix=PREFIX, tags=["positions"])
app.include_router(equity.router,    prefix=PREFIX, tags=["equity"])
app.include_router(quotes.router,    prefix=PREFIX, tags=["quotes"])
app.include_router(demo.router,      prefix=PREFIX, tags=["demo"])
app.include_router(daily.router,         prefix=PREFIX, tags=["equity"])
app.include_router(lots.router,          prefix=PREFIX, tags=["lots"])
app.include_router(todo.router,          prefix=PREFIX, tags=["quotes"])
app.include_router(perf.router,          prefix=PREFIX, tags=["perf"])
app.include_router(rebalance.router,     prefix=PREFIX, tags=["rebalance"])
app.include_router(export_import.router, prefix=PREFIX, tags=["import-export"])
app.include_router(backup.router,        prefix=PREFIX, tags=["system"])


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
def health():
    """Liveness probe."""
    return {"status": "ok"}
