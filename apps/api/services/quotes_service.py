"""Reusable quote-refresh service.

Callable from:
  - POST /api/quotes/refresh  (manual, HTTP request)
  - APScheduler daily job     (schedule)
  - trades router             (trade, background task)
"""
from __future__ import annotations

import datetime
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional

from ..config import DB_PATH
from ..providers.auto import get_provider
from ..tz import TZ
from ledger import StockLedger


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class PriceItem:
    symbol: str
    date: str
    close: float


@dataclass
class ErrorItem:
    symbol: str
    message: str


@dataclass
class RefreshServiceResult:
    as_of: str
    provider: str
    trigger: str
    requested: int
    inserted: int
    skipped: int
    errors: List[ErrorItem] = field(default_factory=list)
    prices: List[PriceItem] = field(default_factory=list)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_log_table() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quote_refresh_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at       TEXT NOT NULL,
                provider     TEXT NOT NULL,
                as_of        TEXT NOT NULL,
                requested    INTEGER NOT NULL DEFAULT 0,
                inserted     INTEGER NOT NULL DEFAULT 0,
                skipped      INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                trigger      TEXT NOT NULL DEFAULT 'manual',
                message      TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Add trigger column if upgrading from older schema
        cols = {r[1] for r in conn.execute("PRAGMA table_info(quote_refresh_log)")}
        if "trigger" not in cols:
            conn.execute("ALTER TABLE quote_refresh_log ADD COLUMN trigger TEXT NOT NULL DEFAULT 'manual'")
        conn.commit()


def _log_run(result: RefreshServiceResult) -> None:
    try:
        _ensure_log_table()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO quote_refresh_log
                    (run_at, provider, as_of, requested, inserted, skipped,
                     errors_count, trigger, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.datetime.now(TZ).isoformat(),
                    result.provider,
                    result.as_of,
                    result.requested,
                    result.inserted,
                    result.skipped,
                    len(result.errors),
                    result.trigger,
                    result.errors[0].message if len(result.errors) == result.requested and result.errors else None,
                ),
            )
            conn.commit()
    except Exception:
        pass


def _has_fresh_quote(symbol: str, as_of: str, max_age_days: int = 2) -> bool:
    """True if a quote exists within *max_age_days* of *as_of*."""
    try:
        as_of_dt = datetime.date.fromisoformat(as_of)
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT date FROM prices WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        if not row:
            return False
        last_dt = datetime.date.fromisoformat(row[0])
        return (as_of_dt - last_dt).days <= max_age_days
    except Exception:
        return False


# ── Core function ─────────────────────────────────────────────────────────────

def refresh_quotes_for_symbols(
    ledger: StockLedger,
    symbols: List[str],
    as_of: str,
    provider_name: str = "auto",
    trigger: str = "manual",
    skip_if_fresh: bool = True,
    max_age_days: int = 2,
) -> RefreshServiceResult:
    """Fetch closing prices for *symbols* and upsert into the prices table.

    Parameters
    ----------
    ledger:         shared StockLedger instance
    symbols:        list of ticker symbols
    as_of:          target date (YYYY-MM-DD)
    provider_name:  "auto" | "twse" | "finmind" | "yahoo"
    trigger:        logging tag – "manual" | "schedule" | "trade"
    skip_if_fresh:  skip symbols that already have a quote within max_age_days
    max_age_days:   freshness window for skip_if_fresh
    """
    if not symbols:
        return RefreshServiceResult(
            as_of=as_of, provider=provider_name, trigger=trigger,
            requested=0, inserted=0, skipped=0,
        )

    # Optionally skip symbols that already have a recent quote
    to_fetch: List[str] = []
    skipped = 0
    if skip_if_fresh:
        for sym in symbols:
            if _has_fresh_quote(sym, as_of, max_age_days):
                skipped += 1
            else:
                to_fetch.append(sym)
    else:
        to_fetch = list(symbols)

    if not to_fetch:
        result = RefreshServiceResult(
            as_of=as_of, provider=provider_name, trigger=trigger,
            requested=len(symbols), inserted=0, skipped=skipped,
        )
        _log_run(result)
        return result

    provider = get_provider(provider_name)
    inserted = 0
    errors: List[ErrorItem] = []
    prices: List[PriceItem] = []

    try:
        bulk = provider.get_bulk_close(to_fetch, as_of)
    except Exception as exc:
        errors = [ErrorItem(symbol=s, message=str(exc)) for s in to_fetch]
        result = RefreshServiceResult(
            as_of=as_of, provider=provider_name, trigger=trigger,
            requested=len(symbols), inserted=0, skipped=skipped, errors=errors,
        )
        _log_run(result)
        return result

    for sym in to_fetch:
        if sym in bulk:
            rec = bulk[sym]
            try:
                ledger.add_price(symbol=rec.symbol, date=rec.date, close=rec.close)
                inserted += 1
                prices.append(PriceItem(symbol=rec.symbol, date=rec.date, close=rec.close))
            except Exception as exc:
                errors.append(ErrorItem(symbol=sym, message=str(exc)))
        else:
            errors.append(ErrorItem(symbol=sym, message="no price data available"))

    result = RefreshServiceResult(
        as_of=as_of,
        provider=provider.name,
        trigger=trigger,
        requested=len(symbols),
        inserted=inserted,
        skipped=skipped,
        errors=errors,
        prices=prices,
    )
    _log_run(result)
    return result
