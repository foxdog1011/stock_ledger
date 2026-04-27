"""Tests for the video pick cooldown system."""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from domain.calendar.cooldown import (
    get_cooldown_sectors,
    get_cooldown_symbols,
    get_recent_picks,
    init_cooldown_tables,
    record_pick,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with cooldown tables."""
    p = tmp_path / "test_cooldown.db"
    init_cooldown_tables(p)
    return p


def test_init_creates_table(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='video_pick_history'"
    ).fetchall()
    conn.close()
    assert len(tables) == 1


def test_record_and_query_symbol(db_path: Path) -> None:
    record_pick(db_path, "2303", slot="morning", data_date="2026-04-20")
    cooldown = get_cooldown_symbols(db_path, days=1)
    assert "2303" in cooldown


def test_record_and_query_sector(db_path: Path) -> None:
    record_pick(
        db_path, "金融", slot="sector", data_date="2026-04-20", sector_name="金融"
    )
    cooldown = get_cooldown_sectors(db_path, days=5)
    assert "金融" in cooldown


def test_cooldown_expiry_symbol(db_path: Path) -> None:
    # Insert a pick with old timestamp
    conn = sqlite3.connect(str(db_path))
    old_ts = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    conn.execute(
        "INSERT INTO video_pick_history (symbol, slot, data_date, picked_at) VALUES (?, ?, ?, ?)",
        ("2330", "morning", "2026-04-15", old_ts),
    )
    conn.commit()
    conn.close()

    # Should NOT appear in 2-day cooldown
    cooldown = get_cooldown_symbols(db_path, days=2)
    assert "2330" not in cooldown


def test_cooldown_expiry_sector(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    conn.execute(
        "INSERT INTO video_pick_history (symbol, sector_name, slot, data_date, picked_at) VALUES (?, ?, ?, ?, ?)",
        ("散熱", "散熱", "sector", "2026-04-10", old_ts),
    )
    conn.commit()
    conn.close()

    cooldown = get_cooldown_sectors(db_path, days=4)
    assert "散熱" not in cooldown


def test_empty_history(db_path: Path) -> None:
    assert get_cooldown_symbols(db_path) == set()
    assert get_cooldown_sectors(db_path) == set()
    assert get_recent_picks(db_path) == []


def test_multiple_picks_tracked(db_path: Path) -> None:
    record_pick(db_path, "2303", slot="morning", data_date="2026-04-20")
    record_pick(db_path, "2317", slot="afternoon", data_date="2026-04-20")
    record_pick(db_path, "2303", slot="afternoon", data_date="2026-04-20")

    cooldown = get_cooldown_symbols(db_path, days=1)
    assert cooldown == {"2303", "2317"}

    recent = get_recent_picks(db_path)
    assert len(recent) == 3


def test_symbol_uppercase(db_path: Path) -> None:
    record_pick(db_path, "tsm", slot="morning", data_date="2026-04-20")
    cooldown = get_cooldown_symbols(db_path, days=1)
    assert "TSM" in cooldown


def test_recent_picks_ordered(db_path: Path) -> None:
    # Insert with explicit timestamps relative to now to stay within the 7-day window
    now = datetime.now(UTC)
    ts_older = (now - timedelta(hours=48)).isoformat()
    ts_newer = (now - timedelta(hours=24)).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO video_pick_history (symbol, slot, data_date, picked_at) VALUES (?, ?, ?, ?)",
        ("2303", "morning", "2026-04-19", ts_older),
    )
    conn.execute(
        "INSERT INTO video_pick_history (symbol, slot, data_date, picked_at) VALUES (?, ?, ?, ?)",
        ("2317", "afternoon", "2026-04-20", ts_newer),
    )
    conn.commit()
    conn.close()

    recent = get_recent_picks(db_path)
    assert recent[0]["symbol"] == "2317"  # most recent first
    assert recent[1]["symbol"] == "2303"


def test_init_prunes_old_entries(tmp_path: Path) -> None:
    p = tmp_path / "prune_test.db"
    init_cooldown_tables(p)

    # Insert an old entry
    conn = sqlite3.connect(str(p))
    old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    conn.execute(
        "INSERT INTO video_pick_history (symbol, slot, data_date, picked_at) VALUES (?, ?, ?, ?)",
        ("OLD", "morning", "2026-03-01", old_ts),
    )
    conn.commit()
    conn.close()

    # Re-init should prune
    init_cooldown_tables(p)

    conn = sqlite3.connect(str(p))
    count = conn.execute("SELECT COUNT(*) FROM video_pick_history").fetchone()[0]
    conn.close()
    assert count == 0
