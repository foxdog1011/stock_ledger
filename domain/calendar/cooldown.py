"""Video pick cooldown & upload deduplication.

Tracks which symbols and sectors were recently used in videos and provides
cooldown sets to exclude them from future picks.  Also logs YouTube uploads
to prevent duplicate uploads of the same (symbol, slot, data_date).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Configurable via environment variables
SYMBOL_COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_SYMBOL_DAYS", "2"))
SECTOR_COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_SECTOR_DAYS", "4"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS video_pick_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    sector_name TEXT,
    slot        TEXT    NOT NULL,
    data_date   TEXT    NOT NULL,
    picked_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pick_history_symbol
    ON video_pick_history(symbol, picked_at);
CREATE INDEX IF NOT EXISTS idx_pick_history_sector
    ON video_pick_history(sector_name, picked_at);

CREATE TABLE IF NOT EXISTS video_upload_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    slot        TEXT    NOT NULL,
    data_date   TEXT    NOT NULL,
    video_id    TEXT    NOT NULL,
    youtube_url TEXT    NOT NULL,
    uploaded_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_upload_log_dedup
    ON video_upload_log(symbol, slot, data_date);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_cooldown_tables(db_path: Path) -> None:
    """Create the video_pick_history and video_upload_log tables if they don't exist."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        # Prune entries older than 30 days
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        conn.execute("DELETE FROM video_pick_history WHERE picked_at < ?", (cutoff,))
        conn.execute("DELETE FROM video_upload_log WHERE uploaded_at < ?", (cutoff,))


def record_pick(
    db_path: Path,
    symbol: str,
    slot: str,
    data_date: str,
    sector_name: str | None = None,
) -> None:
    """Record a pick so it enters cooldown."""
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO video_pick_history (symbol, sector_name, slot, data_date)
               VALUES (?, ?, ?, ?)""",
            (symbol.upper(), sector_name, slot, data_date),
        )
    logger.info("Recorded pick: %s (slot=%s, sector=%s)", symbol, slot, sector_name)


def get_cooldown_symbols(db_path: Path, days: int | None = None) -> set[str]:
    """Return symbols picked in the last N days."""
    days = days if days is not None else SYMBOL_COOLDOWN_DAYS
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM video_pick_history WHERE picked_at >= ?",
            (cutoff,),
        ).fetchall()
    return {r["symbol"] for r in rows}


def get_cooldown_sectors(db_path: Path, days: int | None = None) -> set[str]:
    """Return sector names picked in the last N days."""
    days = days if days is not None else SECTOR_COOLDOWN_DAYS
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT DISTINCT sector_name FROM video_pick_history
               WHERE sector_name IS NOT NULL AND picked_at >= ?""",
            (cutoff,),
        ).fetchall()
    return {r["sector_name"] for r in rows}


def get_today_sectors(db_path: Path) -> set[str]:
    """Return sector names picked today (same calendar date, UTC)."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT DISTINCT sector_name FROM video_pick_history
               WHERE sector_name IS NOT NULL AND date(picked_at) = ?""",
            (today,),
        ).fetchall()
    return {r["sector_name"] for r in rows}


def get_recent_picks(db_path: Path, days: int = 7) -> list[dict]:
    """Return recent pick history for debugging."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT symbol, sector_name, slot, data_date, picked_at
               FROM video_pick_history
               WHERE picked_at >= ?
               ORDER BY picked_at DESC""",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Upload rate limiting ─────────────────────────────────────────────────────


def get_today_upload_count(db_path: Path) -> int:
    """Count uploads recorded today (UTC calendar date)."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM video_upload_log WHERE date(uploaded_at) = ?",
            (today,),
        ).fetchone()
    return row["cnt"] if row else 0


def get_last_upload_time(db_path: Path) -> datetime | None:
    """Return the timestamp of the most recent upload, or None if no uploads exist."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT uploaded_at FROM video_upload_log ORDER BY uploaded_at DESC LIMIT 1",
        ).fetchone()
    if row and row["uploaded_at"]:
        return datetime.fromisoformat(row["uploaded_at"]).replace(tzinfo=UTC)
    return None


# ── Upload deduplication ─────────────────────────────────────────────────────


def find_existing_upload(
    db_path: Path,
    symbol: str,
    slot: str,
    data_date: str,
) -> dict | None:
    """Return the existing upload record if (symbol, slot, data_date) was already uploaded."""
    with _connect(db_path) as conn:
        row = conn.execute(
            """SELECT video_id, youtube_url, uploaded_at
               FROM video_upload_log
               WHERE symbol = ? AND slot = ? AND data_date = ?""",
            (symbol.upper(), slot, data_date),
        ).fetchone()
    if row:
        return dict(row)
    return None


def record_upload(
    db_path: Path,
    symbol: str,
    slot: str,
    data_date: str,
    video_id: str,
    youtube_url: str,
) -> None:
    """Record a successful YouTube upload for deduplication."""
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO video_upload_log
               (symbol, slot, data_date, video_id, youtube_url)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol.upper(), slot, data_date, video_id, youtube_url),
        )
    logger.info(
        "Recorded upload: %s (slot=%s, date=%s) -> %s",
        symbol, slot, data_date, video_id,
    )
