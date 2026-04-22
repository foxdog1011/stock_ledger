"""Shared helpers used across MCP tool modules."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "/data/ledger.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ledger(db_path: str = DB_PATH):
    """Return a fresh StockLedger instance (cheap to construct)."""
    from ledger import StockLedger  # local import keeps startup fast

    return StockLedger(db_path)


def _positions_dict(ledger, as_of=None) -> dict:
    """Return positions keyed by symbol from all_positions_pnl list."""
    rows = ledger.all_positions_pnl(as_of=as_of, open_only=False)
    return {row["symbol"]: row for row in rows}


def _research_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _yf_symbol(symbol: str) -> str:
    """Convert Taiwan numeric ticker to Yahoo Finance format."""
    sym = symbol.upper().strip()
    if sym.isdigit():
        return f"{sym}.TW"
    return sym


def _yf_fetch(yf_ticker, method: str, retries: int = 2, **kwargs):
    """Call a yfinance method with simple retry on transient failures."""
    last_exc: Exception = RuntimeError("no attempts")
    for attempt in range(retries + 1):
        try:
            return getattr(yf_ticker, method)(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1)
    raise last_exc
