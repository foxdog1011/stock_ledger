"""Scenario repository: all direct SQL operations for scenario_plans."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.db import get_connection


# ── constants ─────────────────────────────────────────────────────────────────

UPDATABLE_SCENARIO_FIELDS = frozenset({
    "plan_a", "plan_b", "plan_c", "plan_d",
    "price_target", "stop_loss",
})


# ── internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── table initialisation ──────────────────────────────────────────────────────

def init_scenario_tables(db_path: Path) -> None:
    """Create scenario_plans table if it doesn't exist.  Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scenario_plans (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                catalyst_id  INTEGER NOT NULL
                                 REFERENCES catalysts(id) ON DELETE CASCADE,
                plan_a       TEXT NOT NULL DEFAULT '',
                plan_b       TEXT NOT NULL DEFAULT '',
                plan_c       TEXT NOT NULL DEFAULT '',
                plan_d       TEXT NOT NULL DEFAULT '',
                price_target REAL NULL,
                stop_loss    REAL NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(catalyst_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── scenario plans ────────────────────────────────────────────────────────────

def get_scenario(db_path: Path, catalyst_id: int) -> dict | None:
    """Return scenario_plan dict for the given catalyst, or None."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scenario_plans WHERE catalyst_id = ?", (catalyst_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def upsert_scenario(
    db_path: Path,
    catalyst_id: int,
    updates: dict,
) -> dict:
    """
    Create or partially update the scenario_plan for a catalyst.

    - If no scenario exists yet, creates one with the provided fields.
    - If a scenario already exists, updates only the provided fields
      (partial update — unprovided fields are unchanged).
    - Unknown fields raise ValueError.
    - catalyst_id not found raises ValueError.
    - updated_at is always refreshed.
    """
    unknown = set(updates) - UPDATABLE_SCENARIO_FIELDS
    if unknown:
        raise ValueError(
            f"Unknown scenario fields: {sorted(unknown)}. "
            f"Allowed: {sorted(UPDATABLE_SCENARIO_FIELDS)}"
        )

    # Validate catalyst exists
    conn = get_connection(db_path)
    try:
        existing_catalyst = conn.execute(
            "SELECT id FROM catalysts WHERE id = ?", (catalyst_id,)
        ).fetchone()
        if existing_catalyst is None:
            raise ValueError(f"Catalyst {catalyst_id} not found")

        now = _now()
        existing = conn.execute(
            "SELECT * FROM scenario_plans WHERE catalyst_id = ?", (catalyst_id,)
        ).fetchone()

        if existing is None:
            # INSERT with provided fields
            valid = {k: v for k, v in updates.items() if k in UPDATABLE_SCENARIO_FIELDS}
            columns = ["catalyst_id", "created_at", "updated_at"] + list(valid.keys())
            placeholders = ", ".join("?" for _ in columns)
            values = [catalyst_id, now, now] + list(valid.values())
            conn.execute(
                f"INSERT INTO scenario_plans ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
        else:
            # Partial UPDATE
            valid = {k: v for k, v in updates.items() if k in UPDATABLE_SCENARIO_FIELDS}
            valid["updated_at"] = now
            set_clause = ", ".join(f"{k} = ?" for k in valid)
            conn.execute(
                f"UPDATE scenario_plans SET {set_clause} WHERE catalyst_id = ?",
                list(valid.values()) + [catalyst_id],
            )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM scenario_plans WHERE catalyst_id = ?", (catalyst_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
