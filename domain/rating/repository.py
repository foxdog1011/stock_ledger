"""Investment rating repository: SQL operations."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.db import get_connection
from .models import RATING_VALUES, UPDATABLE_RATING_FIELDS


def _sym(s: str) -> str:
    return s.strip().upper()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_rating_tables(db_path: Path) -> None:
    """Create investment rating tables. Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS investment_ratings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                rating          TEXT NOT NULL,
                target_price    REAL,
                stop_loss       REAL,
                thesis          TEXT NOT NULL DEFAULT '',
                time_horizon    TEXT NOT NULL DEFAULT '12m',
                confidence      REAL DEFAULT 0.5,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_rating_symbol
                ON investment_ratings(symbol);

            CREATE TABLE IF NOT EXISTS scenario_quantitative (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                scenario_name   TEXT NOT NULL,
                target_price    REAL NOT NULL,
                probability     REAL NOT NULL DEFAULT 0.33,
                thesis          TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(symbol, scenario_name)
            );
            CREATE INDEX IF NOT EXISTS idx_scenario_q_symbol
                ON scenario_quantitative(symbol);
        """)
        conn.commit()
    finally:
        conn.close()


# ── Investment Ratings ───────────────────────────────────────────────────────

def upsert_rating(
    db_path: Path,
    symbol: str,
    rating: str,
    target_price: float | None = None,
    stop_loss: float | None = None,
    thesis: str = "",
    time_horizon: str = "12m",
    confidence: float = 0.5,
) -> dict:
    """Create or update an investment rating for a symbol."""
    sym = _sym(symbol)
    if rating not in RATING_VALUES:
        raise ValueError(f"rating must be one of {sorted(RATING_VALUES)}")
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1")

    now = _now()
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM investment_ratings WHERE symbol = ? ORDER BY id DESC LIMIT 1",
            (sym,),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE investment_ratings
                   SET rating=?, target_price=?, stop_loss=?, thesis=?,
                       time_horizon=?, confidence=?, updated_at=?
                   WHERE id=?""",
                (rating, target_price, stop_loss, thesis, time_horizon,
                 confidence, now, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO investment_ratings
                   (symbol, rating, target_price, stop_loss, thesis,
                    time_horizon, confidence, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (sym, rating, target_price, stop_loss, thesis,
                 time_horizon, confidence, now, now),
            )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM investment_ratings WHERE symbol = ? ORDER BY id DESC LIMIT 1",
            (sym,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_rating(db_path: Path, symbol: str) -> dict | None:
    """Return the latest investment rating for a symbol."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM investment_ratings WHERE symbol = ? ORDER BY id DESC LIMIT 1",
            (sym,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_ratings(db_path: Path) -> list[dict]:
    """Return all latest ratings (one per symbol)."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT r.* FROM investment_ratings r
               INNER JOIN (
                   SELECT symbol, MAX(id) AS max_id
                   FROM investment_ratings GROUP BY symbol
               ) latest ON r.id = latest.max_id
               ORDER BY r.updated_at DESC""",
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── Quantitative Scenarios ───────────────────────────────────────────────────

def upsert_scenario_q(
    db_path: Path,
    symbol: str,
    scenario_name: str,
    target_price: float,
    probability: float,
    thesis: str = "",
) -> dict:
    """Create or update a quantitative scenario (bull/base/bear)."""
    sym = _sym(symbol)
    if probability < 0 or probability > 1:
        raise ValueError("probability must be between 0 and 1")

    now = _now()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO scenario_quantitative
               (symbol, scenario_name, target_price, probability, thesis, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(symbol, scenario_name) DO UPDATE SET
               target_price=excluded.target_price,
               probability=excluded.probability,
               thesis=excluded.thesis,
               updated_at=excluded.updated_at""",
            (sym, scenario_name, target_price, probability, thesis, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM scenario_quantitative WHERE symbol=? AND scenario_name=?",
            (sym, scenario_name),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_scenarios_q(db_path: Path, symbol: str) -> list[dict]:
    """Return all quantitative scenarios for a symbol."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM scenario_quantitative WHERE symbol=? ORDER BY probability DESC",
            (sym,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def compute_expected_value(
    db_path: Path,
    symbol: str,
    current_price: float,
) -> dict:
    """Compute probability-weighted expected return from scenarios."""
    scenarios = get_scenarios_q(db_path, symbol)
    if not scenarios:
        return {"symbol": symbol, "scenarios": [], "expected_price": None, "expected_return_pct": None}

    total_prob = sum(s["probability"] for s in scenarios)
    if total_prob == 0:
        return {"symbol": symbol, "scenarios": scenarios, "expected_price": None, "expected_return_pct": None}

    # Normalize probabilities
    expected_price = sum(
        s["target_price"] * (s["probability"] / total_prob)
        for s in scenarios
    )
    expected_return_pct = (expected_price - current_price) / current_price * 100

    enriched = []
    for s in scenarios:
        entry = dict(s)
        entry["return_pct"] = round((s["target_price"] - current_price) / current_price * 100, 2)
        entry["weighted_contribution"] = round(
            s["target_price"] * (s["probability"] / total_prob), 2
        )
        enriched.append(entry)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "scenarios": enriched,
        "expected_price": round(expected_price, 2),
        "expected_return_pct": round(expected_return_pct, 2),
        "total_probability": round(total_prob, 2),
    }
