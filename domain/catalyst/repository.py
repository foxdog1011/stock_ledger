"""Catalyst repository: all direct SQL operations."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.db import get_connection

from .models import EVENT_TYPES, STATUS_VALUES, UPDATABLE_CATALYST_FIELDS


# ── internal helpers ──────────────────────────────────────────────────────────

def _sym(s: str) -> str:
    return s.strip().upper()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── table initialisation ──────────────────────────────────────────────────────

def init_catalyst_tables(db_path: Path) -> None:
    """Create catalysts table if it doesn't exist.  Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS catalysts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                symbol      TEXT NULL,
                title       TEXT NOT NULL,
                event_date  TEXT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                notes       TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── catalysts ─────────────────────────────────────────────────────────────────

def create_catalyst(
    db_path: Path,
    event_type: str,
    title: str,
    symbol: str | None = None,
    event_date: str | None = None,
    notes: str = "",
) -> dict:
    """
    Create a new catalyst.

    Raises ValueError for invalid event_type.
    symbol is normalised (strip + upper) when provided.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {sorted(EVENT_TYPES)}")

    sym = _sym(symbol) if symbol is not None else None
    now = _now()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO catalysts
                (event_type, symbol, title, event_date, status, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (event_type, sym, title.strip(), event_date, "pending", notes, now, now),
        )
        row = conn.execute(
            "SELECT * FROM catalysts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_catalyst(db_path: Path, catalyst_id: int) -> dict | None:
    """Return catalyst dict or None if not found."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM catalysts WHERE id = ?", (catalyst_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_catalysts(
    db_path: Path,
    symbol: str | None = None,
    status: str | None = None,
    event_type: str | None = None,
) -> list[dict]:
    """Return catalysts sorted by event_date ASC (NULLs last), then id ASC."""
    if status is not None and status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")
    if event_type is not None and event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {sorted(EVENT_TYPES)}")

    query = "SELECT * FROM catalysts WHERE 1=1"
    params: list = []

    if symbol is not None:
        query += " AND symbol = ?"
        params.append(_sym(symbol))
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    if event_type is not None:
        query += " AND event_type = ?"
        params.append(event_type)

    query += " ORDER BY event_date ASC NULLS LAST, id ASC"

    conn = get_connection(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def update_catalyst(
    db_path: Path,
    catalyst_id: int,
    updates: dict,
) -> dict | None:
    """
    Partially update a catalyst.

    Only keys in UPDATABLE_CATALYST_FIELDS are accepted.
    Unknown fields raise ValueError.
    updated_at is always refreshed.
    Returns None if catalyst_id is not found.
    Raises ValueError for invalid field names or invalid status value.
    """
    unknown = set(updates) - UPDATABLE_CATALYST_FIELDS
    if unknown:
        raise ValueError(
            f"Unknown update fields: {sorted(unknown)}. "
            f"Allowed: {sorted(UPDATABLE_CATALYST_FIELDS)}"
        )

    if "status" in updates and updates["status"] not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")

    valid = dict(updates)
    if not valid:
        return get_catalyst(db_path, catalyst_id)

    valid["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in valid)
    values = list(valid.values()) + [catalyst_id]

    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            f"UPDATE catalysts SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT * FROM catalysts WHERE id = ?", (catalyst_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
