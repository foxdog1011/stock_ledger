"""Watchlist repository: all direct SQL operations.

FK enforcement
--------------
All connections go through ``_get_conn()``, which issues
``PRAGMA foreign_keys = ON`` after opening.  This enforces
``watchlist_items.watchlist_id REFERENCES watchlists(id)``.
Existing ``get_connection()`` callers are unaffected.

Symbol normalisation
--------------------
Every symbol is normalised via ``_sym()`` (strip + upper).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.db import get_connection

from .models import STATUS_VALUES, UPDATABLE_ITEM_FIELDS


# ── internal helpers ──────────────────────────────────────────────────────────

def _get_conn(db_path: Path) -> sqlite3.Connection:
    """Wrap get_connection with PRAGMA foreign_keys = ON."""
    conn = get_connection(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _sym(s: str) -> str:
    return s.strip().upper()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── table initialisation ──────────────────────────────────────────────────────

def init_watchlist_tables(db_path: Path) -> None:
    """Create watchlist tables if they don't exist.  Idempotent."""
    conn = _get_conn(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_items (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id      INTEGER NOT NULL
                                      REFERENCES watchlists(id) ON DELETE CASCADE,
                symbol            TEXT NOT NULL,
                industry_position TEXT NOT NULL DEFAULT '',
                operation_focus   TEXT NOT NULL DEFAULT '',
                thesis_summary    TEXT NOT NULL DEFAULT '',
                primary_catalyst  TEXT NOT NULL DEFAULT '',
                status            TEXT NOT NULL DEFAULT 'watching',
                added_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(watchlist_id, symbol)
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── watchlists ────────────────────────────────────────────────────────────────

def create_watchlist(
    db_path: Path,
    name: str,
    description: str = "",
) -> dict:
    """Create a new watchlist.  Raises ValueError if name already exists."""
    now = _now()
    conn = _get_conn(db_path)
    try:
        try:
            conn.execute(
                """
                INSERT INTO watchlists (name, description, created_at, updated_at)
                VALUES (?,?,?,?)
                """,
                (name.strip(), description, now, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Watchlist name '{name.strip()}' already exists")
        row = conn.execute(
            "SELECT * FROM watchlists WHERE name = ?", (name.strip(),)
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_watchlist(db_path: Path, watchlist_id: int) -> dict | None:
    """Return watchlist dict or None if not found."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_watchlists(db_path: Path) -> list[dict]:
    """Return all watchlists sorted by name."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM watchlists ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# ── watchlist items ───────────────────────────────────────────────────────────

def add_watchlist_item(
    db_path: Path,
    watchlist_id: int,
    symbol: str,
    industry_position: str = "",
    operation_focus: str = "",
    thesis_summary: str = "",
    primary_catalyst: str = "",
    status: str = "watching",
) -> dict:
    """
    Add a symbol to a watchlist.

    Raises ValueError for:
    - invalid status
    - watchlist_id not found
    - duplicate (watchlist_id, symbol)
    """
    sym = _sym(symbol)

    if status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")

    # Python-layer check (FK also enforces at DB level)
    if get_watchlist(db_path, watchlist_id) is None:
        raise ValueError(f"Watchlist {watchlist_id} not found")

    now = _now()
    conn = _get_conn(db_path)
    try:
        try:
            conn.execute(
                """
                INSERT INTO watchlist_items
                    (watchlist_id, symbol, industry_position, operation_focus,
                     thesis_summary, primary_catalyst, status, added_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (watchlist_id, sym, industry_position, operation_focus,
                 thesis_summary, primary_catalyst, status, now, now),
            )
        except sqlite3.IntegrityError as e:
            err = str(e).lower()
            if "foreign key" in err:
                raise ValueError(f"Watchlist {watchlist_id} not found")
            raise ValueError(
                f"Symbol '{sym}' already in watchlist {watchlist_id}"
            )
        row = conn.execute(
            "SELECT * FROM watchlist_items WHERE watchlist_id = ? AND symbol = ?",
            (watchlist_id, sym),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def list_watchlist_items(
    db_path: Path,
    watchlist_id: int,
    include_archived: bool = False,
) -> list[dict]:
    """
    Return items for a watchlist, oldest first.

    include_archived=False (default) excludes status='archived'.
    """
    conn = _get_conn(db_path)
    try:
        query  = "SELECT * FROM watchlist_items WHERE watchlist_id = ?"
        params: list = [watchlist_id]
        if not include_archived:
            query += " AND status != 'archived'"
        query += " ORDER BY added_at ASC, id ASC"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def update_watchlist_item(
    db_path: Path,
    item_id: int,
    updates: dict,
) -> dict | None:
    """
    Partially update a watchlist item.

    Only keys in UPDATABLE_ITEM_FIELDS are applied; others are silently ignored.
    ``updated_at`` is always refreshed.
    Returns None if item_id is not found.
    Raises ValueError for invalid status value.
    """
    valid = {k: v for k, v in updates.items() if k in UPDATABLE_ITEM_FIELDS}
    if not valid:
        conn = _get_conn(db_path)
        try:
            row = conn.execute(
                "SELECT * FROM watchlist_items WHERE id = ?", (item_id,)
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row else None

    if "status" in valid and valid["status"] not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")

    valid["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in valid)
    values = list(valid.values()) + [item_id]

    conn = _get_conn(db_path)
    try:
        cur = conn.execute(
            f"UPDATE watchlist_items SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT * FROM watchlist_items WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
