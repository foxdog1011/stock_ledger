"""Content calendar SQLite repository — stores planned YouTube episodes."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS content_calendar (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_date  TEXT    NOT NULL,
    day_of_week     INTEGER NOT NULL,
    content_type    TEXT    NOT NULL,
    title           TEXT    NOT NULL DEFAULT '',
    symbol          TEXT,
    sector_name     TEXT,
    symbols_json    TEXT    DEFAULT '[]',
    source          TEXT    NOT NULL DEFAULT 'auto',
    status          TEXT    NOT NULL DEFAULT 'planned',
    priority        INTEGER NOT NULL DEFAULT 0,
    pick_reason     TEXT    DEFAULT '',
    video_path      TEXT,
    youtube_id      TEXT,
    youtube_url     TEXT,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    metadata_json   TEXT    DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_calendar_date   ON content_calendar(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_calendar_status ON content_calendar(status);
"""


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["symbols"] = json.loads(d.pop("symbols_json", "[]"))
    d["metadata"] = json.loads(d.pop("metadata_json", "{}"))
    d.pop("_sort_group", None)  # internal column from UNION queries
    return d


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_calendar_tables(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        # Migration: add retry_count if missing (existing databases)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(content_calendar)")}
        if "retry_count" not in cols:
            conn.execute("ALTER TABLE content_calendar ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")


def insert_episode(db_path: Path, episode: dict[str, Any]) -> dict:
    sql = """
        INSERT OR REPLACE INTO content_calendar
            (scheduled_date, day_of_week, content_type, title, symbol,
             sector_name, symbols_json, source, status, priority,
             pick_reason, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    now = _now()
    from datetime import date as _date
    dt = _date.fromisoformat(episode["scheduled_date"])
    vals = (
        episode["scheduled_date"],
        dt.weekday(),
        episode["content_type"],
        episode.get("title", ""),
        episode.get("symbol"),
        episode.get("sector_name"),
        json.dumps(episode.get("symbols", []), ensure_ascii=False),
        episode.get("source", "manual"),
        episode.get("status", "planned"),
        episode.get("priority", 0),
        episode.get("pick_reason", ""),
        json.dumps(episode.get("metadata", {}), ensure_ascii=False),
        now,
        now,
    )
    with _connect(db_path) as conn:
        cur = conn.execute(sql, vals)
        conn.commit()
        row_id = cur.lastrowid
    return get_episode(db_path, row_id)  # type: ignore[arg-type]


def get_episode(db_path: Path, episode_id: int) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM content_calendar WHERE id = ?", (episode_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_episodes(
    db_path: Path,
    start: str | None = None,
    end: str | None = None,
    status: str | None = None,
    content_type: str | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if start:
        clauses.append("scheduled_date >= ?")
        params.append(start)
    if end:
        clauses.append("scheduled_date <= ?")
        params.append(end)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if content_type:
        clauses.append("content_type = ?")
        params.append(content_type)

    where = " AND ".join(clauses) if clauses else "1=1"
    sql = f"SELECT * FROM content_calendar WHERE {where} ORDER BY scheduled_date, priority DESC"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_episode(db_path: Path, episode_id: int, updates: dict[str, Any]) -> dict | None:
    allowed = {
        "scheduled_date", "content_type", "title", "symbol",
        "sector_name", "symbols", "status", "priority",
        "pick_reason", "metadata", "video_path", "youtube_id",
        "youtube_url", "error_message",
    }
    sets: list[str] = []
    vals: list[Any] = []
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "symbols":
            sets.append("symbols_json = ?")
            vals.append(json.dumps(v, ensure_ascii=False))
        elif k == "metadata":
            sets.append("metadata_json = ?")
            vals.append(json.dumps(v, ensure_ascii=False))
        elif k == "scheduled_date":
            from datetime import date as _date
            sets.append("scheduled_date = ?")
            vals.append(v)
            sets.append("day_of_week = ?")
            vals.append(_date.fromisoformat(v).weekday())
        else:
            sets.append(f"{k} = ?")
            vals.append(v)

    if not sets:
        return get_episode(db_path, episode_id)

    sets.append("updated_at = ?")
    vals.append(_now())
    vals.append(episode_id)

    sql = f"UPDATE content_calendar SET {', '.join(sets)} WHERE id = ?"
    with _connect(db_path) as conn:
        conn.execute(sql, vals)
    return get_episode(db_path, episode_id)


def delete_episode(db_path: Path, episode_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM content_calendar WHERE id = ?", (episode_id,))
    return cur.rowcount > 0


def get_next_pending(db_path: Path, max_retries: int = 3) -> dict | None:
    """Get the next episode to produce.

    Priority order:
      1. Planned episodes where scheduled_date <= today (highest priority first)
      2. Failed episodes with retry_count < max_retries (oldest failure first)
    """
    from datetime import date as _date
    today = _date.today().isoformat()

    sql = """
        SELECT *, 0 AS _sort_group FROM content_calendar
        WHERE status = 'planned' AND scheduled_date <= ?
        UNION ALL
        SELECT *, 1 AS _sort_group FROM content_calendar
        WHERE status = 'failed' AND retry_count < ? AND scheduled_date <= ?
        ORDER BY _sort_group ASC, priority DESC, scheduled_date ASC
        LIMIT 1
    """
    with _connect(db_path) as conn:
        row = conn.execute(sql, (today, max_retries, today)).fetchone()
    return _row_to_dict(row) if row else None


def mark_status(
    db_path: Path,
    episode_id: int,
    status: str,
    **extras: Any,
) -> None:
    sets = ["status = ?", "updated_at = ?"]
    vals: list[Any] = [status, _now()]
    if status == "failed":
        sets.append("retry_count = retry_count + 1")
    elif status == "planned":
        # Reset retry count when re-queued manually
        sets.append("retry_count = 0")
    for k in ("video_path", "youtube_id", "youtube_url", "error_message"):
        if k in extras:
            sets.append(f"{k} = ?")
            vals.append(extras[k])
    vals.append(episode_id)
    sql = f"UPDATE content_calendar SET {', '.join(sets)} WHERE id = ?"
    with _connect(db_path) as conn:
        conn.execute(sql, vals)


def clear_auto_episodes(db_path: Path, start: str, end: str) -> int:
    """Delete auto-planned entries that haven't been processed yet."""
    sql = """
        DELETE FROM content_calendar
        WHERE source = 'auto' AND status = 'planned'
          AND scheduled_date >= ? AND scheduled_date <= ?
    """
    with _connect(db_path) as conn:
        cur = conn.execute(sql, (start, end))
    return cur.rowcount
