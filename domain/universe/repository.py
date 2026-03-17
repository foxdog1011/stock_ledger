"""Universe repository: all direct SQL operations.

All functions accept ``db_path: Path`` (not StockLedger) so the universe
layer can be used independently of the ledger domain.

Symbol normalisation
--------------------
Every function normalises symbol / related_symbol via ``_sym()``
(strip + upper) before any DB operation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.db import get_connection

from .models import RELATIONSHIP_TYPES, THESIS_TYPES, UPDATABLE_COMPANY_FIELDS


# ── internal helpers ──────────────────────────────────────────────────────────

def _sym(s: str) -> str:
    return s.strip().upper()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── table initialisation ──────────────────────────────────────────────────────

def init_universe_tables(db_path: Path) -> None:
    """Create universe tables if they don't exist.  Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_master (
                symbol         TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                exchange       TEXT,
                sector         TEXT,
                industry       TEXT,
                business_model TEXT,
                country        TEXT,
                currency       TEXT,
                note           TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_segments (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT NOT NULL,
                segment_name TEXT NOT NULL,
                description  TEXT NOT NULL DEFAULT '',
                revenue_pct  REAL,
                note         TEXT NOT NULL DEFAULT '',
                UNIQUE(symbol, segment_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_relationships (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol            TEXT NOT NULL,
                related_symbol    TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                note              TEXT NOT NULL DEFAULT '',
                UNIQUE(symbol, related_symbol, relationship_type)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_thesis (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                thesis_type TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                is_active   INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── company master ────────────────────────────────────────────────────────────

def add_company(
    db_path: Path,
    symbol: str,
    name: str,
    exchange: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    business_model: str | None = None,
    country: str | None = None,
    currency: str | None = None,
    note: str = "",
) -> dict:
    """Insert a new company.  Raises ValueError if symbol already exists."""
    sym = _sym(symbol)
    now = _now()
    conn = get_connection(db_path)
    try:
        try:
            conn.execute(
                """
                INSERT INTO company_master
                    (symbol, name, exchange, sector, industry, business_model,
                     country, currency, note, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (sym, name, exchange, sector, industry, business_model,
                 country, currency, note, now, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Company '{sym}' already exists")
        row = conn.execute(
            "SELECT * FROM company_master WHERE symbol = ?", (sym,)
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_company(db_path: Path, symbol: str) -> dict | None:
    """Return company dict or None if not found."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM company_master WHERE symbol = ?", (sym,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_companies(db_path: Path) -> list[dict]:
    """Return all companies sorted by symbol."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM company_master ORDER BY symbol"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def update_company(db_path: Path, symbol: str, updates: dict) -> dict | None:
    """
    Partially update company fields.

    Only keys present in UPDATABLE_COMPANY_FIELDS are applied; all others are
    silently ignored.  ``updated_at`` is always refreshed.

    Returns the updated company dict, or None if the symbol is not found.
    """
    sym = _sym(symbol)
    valid = {k: v for k, v in updates.items() if k in UPDATABLE_COMPANY_FIELDS}
    if not valid:
        return get_company(db_path, sym)

    valid["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in valid)
    values = list(valid.values()) + [sym]

    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            f"UPDATE company_master SET {set_clause} WHERE symbol = ?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT * FROM company_master WHERE symbol = ?", (sym,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


# ── company relationships ─────────────────────────────────────────────────────

def add_relationship(
    db_path: Path,
    symbol: str,
    related_symbol: str,
    relationship_type: str,
    note: str = "",
) -> dict:
    """
    Add a directional relationship from symbol → related_symbol.

    related_symbol does not need to exist in company_master.
    Raises ValueError for unknown relationship_type, non-existent symbol,
    or duplicate (symbol, related_symbol, relationship_type).
    """
    sym     = _sym(symbol)
    rel_sym = _sym(related_symbol)
    rel_type = relationship_type.strip().lower()

    if rel_type not in RELATIONSHIP_TYPES:
        raise ValueError(
            f"relationship_type must be one of {sorted(RELATIONSHIP_TYPES)}"
        )
    if get_company(db_path, sym) is None:
        raise ValueError(f"Company '{sym}' not found")

    conn = get_connection(db_path)
    try:
        try:
            conn.execute(
                """
                INSERT INTO company_relationships
                    (symbol, related_symbol, relationship_type, note)
                VALUES (?,?,?,?)
                """,
                (sym, rel_sym, rel_type, note),
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                f"Relationship ({sym}, {rel_sym}, {rel_type}) already exists"
            )
        row = conn.execute(
            """
            SELECT * FROM company_relationships
            WHERE symbol = ? AND related_symbol = ? AND relationship_type = ?
            """,
            (sym, rel_sym, rel_type),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def list_relationships(db_path: Path, symbol: str) -> list[dict]:
    """Return all relationships for symbol, sorted by type then related_symbol."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM company_relationships
            WHERE symbol = ?
            ORDER BY relationship_type, related_symbol
            """,
            (sym,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── company thesis ────────────────────────────────────────────────────────────

def add_thesis(
    db_path: Path,
    symbol: str,
    thesis_type: str,
    content: str,
) -> dict:
    """
    Add a thesis entry for symbol.

    Raises ValueError for unknown thesis_type or non-existent symbol.
    """
    sym    = _sym(symbol)
    t_type = thesis_type.strip().lower()

    if t_type not in THESIS_TYPES:
        raise ValueError(
            f"thesis_type must be one of {sorted(THESIS_TYPES)}"
        )
    if get_company(db_path, sym) is None:
        raise ValueError(f"Company '{sym}' not found")

    now = _now()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO company_thesis (symbol, thesis_type, content, created_at)
            VALUES (?,?,?,?)
            """,
            (sym, t_type, content, now),
        )
        row = conn.execute(
            "SELECT * FROM company_thesis WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def list_thesis(
    db_path: Path,
    symbol: str,
    active_only: bool = True,
) -> list[dict]:
    """Return thesis entries for symbol, newest first."""
    sym = _sym(symbol)
    conn = get_connection(db_path)
    try:
        query  = "SELECT * FROM company_thesis WHERE symbol = ?"
        params: list = [sym]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY created_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def deactivate_thesis(db_path: Path, thesis_id: int) -> None:
    """
    Soft-delete a thesis entry by setting is_active = 0.

    Raises ValueError if the entry does not exist or is already inactive.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, is_active FROM company_thesis WHERE id = ?", (thesis_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Thesis {thesis_id} not found")
        if not row["is_active"]:
            raise ValueError(f"Thesis {thesis_id} is already inactive")
        conn.execute(
            "UPDATE company_thesis SET is_active = 0 WHERE id = ?", (thesis_id,)
        )
        conn.commit()
    finally:
        conn.close()
