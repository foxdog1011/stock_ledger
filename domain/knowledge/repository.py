"""Knowledge SQLite repository."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import KnowledgeEntry


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'web',
    title           TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    tickers         TEXT NOT NULL DEFAULT '[]',
    tags            TEXT NOT NULL DEFAULT '[]',
    quality_tier    TEXT NOT NULL DEFAULT 'unreviewed',
    bull_case       TEXT NOT NULL DEFAULT '',
    bear_case       TEXT NOT NULL DEFAULT '',
    audit_notes     TEXT NOT NULL DEFAULT '',
    quality_score   REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    obsidian_path   TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_knowledge_tickers ON knowledge_entries(tickers);
CREATE INDEX IF NOT EXISTS idx_knowledge_created ON knowledge_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_url ON knowledge_entries(url);
"""


def init_knowledge_tables(db_path: str) -> None:
    """Create knowledge tables if they don't exist."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_CREATE_TABLE + _CREATE_INDEX)
        con.commit()
    finally:
        con.close()


def _row_to_entry(row: sqlite3.Row) -> KnowledgeEntry:
    return KnowledgeEntry(
        id=row["id"],
        url=row["url"],
        source_type=row["source_type"],
        title=row["title"],
        content=row["content"],
        summary=row["summary"],
        tickers=json.loads(row["tickers"]),
        tags=json.loads(row["tags"]),
        quality_tier=row["quality_tier"],
        bull_case=row["bull_case"],
        bear_case=row["bear_case"],
        audit_notes=row["audit_notes"],
        quality_score=row["quality_score"],
        created_at=row["created_at"],
        obsidian_path=row["obsidian_path"],
    )


def insert_entry(
    db_path: str,
    url: str,
    source_type: str,
    title: str,
    content: str,
    summary: str,
    tickers: list[str],
    tags: list[str],
    quality_tier: str,
    bull_case: str,
    bear_case: str,
    audit_notes: str,
    quality_score: float,
    obsidian_path: str,
) -> int:
    """Insert a knowledge entry. Returns the new row ID."""
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(
            """INSERT INTO knowledge_entries
               (url, source_type, title, content, summary, tickers, tags,
                quality_tier, bull_case, bear_case, audit_notes,
                quality_score, obsidian_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                url, source_type, title, content, summary,
                json.dumps(tickers, ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False),
                quality_tier, bull_case, bear_case, audit_notes,
                quality_score, obsidian_path,
            ),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]
    finally:
        con.close()


def get_entry(db_path: str, entry_id: int) -> KnowledgeEntry | None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None
    finally:
        con.close()


def get_by_url(db_path: str, url: str) -> KnowledgeEntry | None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM knowledge_entries WHERE url = ?", (url,)
        ).fetchone()
        return _row_to_entry(row) if row else None
    finally:
        con.close()


def list_entries(
    db_path: str,
    limit: int = 50,
    offset: int = 0,
    ticker: str | None = None,
    tag: str | None = None,
    quality_tier: str | None = None,
) -> list[KnowledgeEntry]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM knowledge_entries WHERE 1=1"
        params: list = []
        if ticker:
            query += " AND tickers LIKE ?"
            params.append(f'%"{ticker}"%')
        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        if quality_tier:
            query += " AND quality_tier = ?"
            params.append(quality_tier)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = con.execute(query, params).fetchall()
        return [_row_to_entry(r) for r in rows]
    finally:
        con.close()


def update_review(
    db_path: str,
    entry_id: int,
    quality_tier: str,
    bull_case: str,
    bear_case: str,
    audit_notes: str,
    quality_score: float,
) -> bool:
    """Update the AI review fields for an entry."""
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(
            """UPDATE knowledge_entries
               SET quality_tier = ?, bull_case = ?, bear_case = ?,
                   audit_notes = ?, quality_score = ?
               WHERE id = ?""",
            (quality_tier, bull_case, bear_case, audit_notes,
             quality_score, entry_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def count_entries(db_path: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()
        return row[0] if row else 0
    finally:
        con.close()
