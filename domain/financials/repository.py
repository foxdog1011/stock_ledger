"""Financial statements repository: SQL operations for quarterly/annual data."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.db import get_connection


def _sym(s: str) -> str:
    return s.strip().upper()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_financials_tables(db_path: Path) -> None:
    """Create financial_statements table. Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS financial_statements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                date            TEXT NOT NULL,
                type            TEXT NOT NULL,
                origin_name     TEXT NOT NULL,
                value           REAL,
                fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(symbol, date, type, origin_name)
            );
            CREATE INDEX IF NOT EXISTS idx_fin_symbol ON financial_statements(symbol);
            CREATE INDEX IF NOT EXISTS idx_fin_date ON financial_statements(date);

            CREATE TABLE IF NOT EXISTS valuation_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                date            TEXT NOT NULL,
                per             REAL,
                pbr             REAL,
                dividend_yield  REAL,
                fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_val_symbol ON valuation_metrics(symbol);

            CREATE TABLE IF NOT EXISTS dividend_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                date            TEXT NOT NULL,
                cash_dividend   REAL,
                stock_dividend  REAL,
                fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(symbol, date)
            );

            CREATE TABLE IF NOT EXISTS tdcc_distribution (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                date            TEXT NOT NULL,
                level           TEXT NOT NULL,
                people          INTEGER,
                shares          INTEGER,
                pct             REAL,
                fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(symbol, date, level)
            );
            CREATE INDEX IF NOT EXISTS idx_tdcc_symbol ON tdcc_distribution(symbol);
        """)
        conn.commit()
    finally:
        conn.close()


# ── Financial Statements ─────────────────────────────────────────────────────

def store_financial_rows(
    db_path: Path,
    symbol: str,
    stmt_type: str,
    rows: list[dict],
) -> int:
    """Store raw FinMind financial data rows. Returns count of inserted rows."""
    sym = _sym(symbol)
    now = _now()
    conn = get_connection(db_path)
    inserted = 0
    try:
        for row in rows:
            date = row.get("date", "")
            origin = row.get("origin_name", row.get("type", ""))
            value = row.get("value")
            if not date or not origin:
                continue
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO financial_statements
                       (symbol, date, type, origin_name, value, fetched_at)
                       VALUES (?,?,?,?,?,?)""",
                    (sym, date, stmt_type, origin, value, now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    finally:
        conn.close()
    return inserted


def get_financial_statements(
    db_path: Path,
    symbol: str,
    stmt_type: str,
    limit: int = 20,
) -> list[dict]:
    """Return financial statement data grouped by date."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT date, origin_name, value
               FROM financial_statements
               WHERE symbol = ? AND type = ?
               ORDER BY date DESC, origin_name""",
            (sym, stmt_type),
        ).fetchall()
    finally:
        conn.close()

    # Group by date → pivot into per-date dicts
    from collections import OrderedDict
    grouped: OrderedDict[str, dict] = OrderedDict()
    for r in rows:
        d = r["date"]
        if d not in grouped:
            grouped[d] = {"date": d}
        grouped[d][r["origin_name"]] = r["value"]

    result = list(grouped.values())
    return result[:limit]


# ── Valuation Metrics (PER/PBR) ─────────────────────────────────────────────

def store_valuation_rows(
    db_path: Path,
    symbol: str,
    rows: list[dict],
) -> int:
    """Store PER/PBR/DividendYield data from FinMind."""
    sym = _sym(symbol)
    now = _now()
    conn = get_connection(db_path)
    inserted = 0
    try:
        for row in rows:
            date = row.get("date", "")
            per = row.get("PER") or row.get("per")
            pbr = row.get("PBR") or row.get("pbr")
            div_yield = row.get("dividend_yield") or row.get("DividendYield")
            if not date:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO valuation_metrics
                   (symbol, date, per, pbr, dividend_yield, fetched_at)
                   VALUES (?,?,?,?,?,?)""",
                (sym, date, per, pbr, div_yield, now),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def get_valuation_metrics(
    db_path: Path,
    symbol: str,
    limit: int = 60,
) -> list[dict]:
    """Return latest valuation metric records."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT date, per, pbr, dividend_yield
               FROM valuation_metrics
               WHERE symbol = ?
               ORDER BY date DESC LIMIT ?""",
            (sym, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Dividend History ─────────────────────────────────────────────────────────

def store_dividend_rows(
    db_path: Path,
    symbol: str,
    rows: list[dict],
) -> int:
    """Store dividend data from FinMind."""
    sym = _sym(symbol)
    now = _now()
    conn = get_connection(db_path)
    inserted = 0
    try:
        for row in rows:
            date = row.get("date", "")
            cash_div = row.get("CashEarningsDistribution") or row.get("cash_dividend", 0)
            stock_div = row.get("StockEarningsDistribution") or row.get("stock_dividend", 0)
            if not date:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO dividend_history
                   (symbol, date, cash_dividend, stock_dividend, fetched_at)
                   VALUES (?,?,?,?,?)""",
                (sym, date, cash_div, stock_div, now),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def get_dividend_history(
    db_path: Path,
    symbol: str,
    limit: int = 20,
) -> list[dict]:
    """Return dividend history for a symbol."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT date, cash_dividend, stock_dividend
               FROM dividend_history
               WHERE symbol = ?
               ORDER BY date DESC LIMIT ?""",
            (sym, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── TDCC Distribution ────────────────────────────────────────────────────────

def store_tdcc_rows(
    db_path: Path,
    symbol: str,
    rows: list[dict],
) -> int:
    """Store TDCC shareholding distribution data."""
    sym = _sym(symbol)
    now = _now()
    conn = get_connection(db_path)
    inserted = 0
    try:
        for row in rows:
            date = row.get("date", "")
            level = row.get("HoldingSharesLevel", "")
            people = row.get("people", 0)
            shares = row.get("unit", row.get("shares", 0))
            pct = row.get("percent", row.get("pct", 0))
            if not date or not level:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO tdcc_distribution
                   (symbol, date, level, people, shares, pct, fetched_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (sym, date, level, people, shares, pct, now),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def get_tdcc_distribution(
    db_path: Path,
    symbol: str,
    limit: int = 1,
) -> list[dict]:
    """Return TDCC data for the latest N dates."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        # Get latest N distinct dates
        dates = conn.execute(
            """SELECT DISTINCT date FROM tdcc_distribution
               WHERE symbol = ? ORDER BY date DESC LIMIT ?""",
            (sym, limit),
        ).fetchall()
        if not dates:
            return []
        date_list = [d["date"] for d in dates]
        placeholders = ",".join("?" * len(date_list))
        rows = conn.execute(
            f"""SELECT date, level, people, shares, pct
                FROM tdcc_distribution
                WHERE symbol = ? AND date IN ({placeholders})
                ORDER BY date DESC, level""",
            [sym] + date_list,
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
