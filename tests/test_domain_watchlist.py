"""Tests for domain.watchlist repository and service."""
import tempfile
import unittest
from pathlib import Path

from ledger import StockLedger
from domain.watchlist.repository import (
    init_watchlist_tables,
    create_watchlist,
    get_watchlist,
    list_watchlists,
    add_watchlist_item,
    list_watchlist_items,
    update_watchlist_item,
)
from domain.watchlist.service import get_watchlist_coverage, list_watchlist_gaps
from domain.universe.repository import init_universe_tables
from ledger.db import get_connection


def _db() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    p = Path(tmp.name)
    init_watchlist_tables(p)
    return p


def _ledger_with_positions() -> tuple[StockLedger, Path]:
    """Ledger with 2 open positions: AAPL (10 shares) and TSLA (5 shares)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    lg = StockLedger(db_path=tmp.name)
    lg.add_cash(500_000, "2024-01-01")
    lg.add_trade("AAPL", "buy", 10, 180.0, "2024-01-10")
    lg.add_trade("TSLA", "buy",  5, 300.0, "2024-01-10")
    return lg, Path(tmp.name)


def _ledger_empty() -> tuple[StockLedger, Path]:
    """Ledger with no positions."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    lg = StockLedger(db_path=tmp.name)
    return lg, Path(tmp.name)


# ── init idempotency ──────────────────────────────────────────────────────────

class TestInit(unittest.TestCase):
    def test_double_init_no_error(self):
        db = _db()
        init_watchlist_tables(db)


# ── create / list watchlists ──────────────────────────────────────────────────

class TestCreateWatchlist(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_create_and_get(self):
        r = create_watchlist(self.db, "Main", "My primary watchlist")
        self.assertEqual(r["name"], "Main")
        self.assertEqual(r["description"], "My primary watchlist")
        self.assertIsNotNone(r["id"])

    def test_timestamps_set(self):
        r = create_watchlist(self.db, "Main")
        self.assertRegex(r["created_at"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertRegex(r["updated_at"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_duplicate_name_raises(self):
        create_watchlist(self.db, "Main")
        with self.assertRaises(ValueError):
            create_watchlist(self.db, "Main")

    def test_list_empty(self):
        self.assertEqual(list_watchlists(self.db), [])

    def test_list_sorted_by_name(self):
        create_watchlist(self.db, "Zebra")
        create_watchlist(self.db, "Alpha")
        names = [r["name"] for r in list_watchlists(self.db)]
        self.assertEqual(names, sorted(names))

    def test_get_not_found_returns_none(self):
        self.assertIsNone(get_watchlist(self.db, 99999))


# ── add / list watchlist items ────────────────────────────────────────────────

class TestWatchlistItems(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        self.wl = create_watchlist(self.db, "Main")
        self.wl_id = self.wl["id"]

    def test_add_and_list(self):
        add_watchlist_item(self.db, self.wl_id, "AAPL", thesis_summary="AI plays")
        items = list_watchlist_items(self.db, self.wl_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "AAPL")
        self.assertEqual(items[0]["thesis_summary"], "AI plays")

    def test_symbol_normalised(self):
        add_watchlist_item(self.db, self.wl_id, " aapl ")
        items = list_watchlist_items(self.db, self.wl_id)
        self.assertEqual(items[0]["symbol"], "AAPL")

    def test_default_status_watching(self):
        add_watchlist_item(self.db, self.wl_id, "AAPL")
        self.assertEqual(list_watchlist_items(self.db, self.wl_id)[0]["status"], "watching")

    def test_all_valid_status_values(self):
        for i, s in enumerate(["watching", "monitoring", "archived"]):
            add_watchlist_item(self.db, self.wl_id, f"SYM{i}", status=s)

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            add_watchlist_item(self.db, self.wl_id, "AAPL", status="active")

    def test_duplicate_symbol_same_watchlist_raises(self):
        add_watchlist_item(self.db, self.wl_id, "AAPL")
        with self.assertRaises(ValueError):
            add_watchlist_item(self.db, self.wl_id, "AAPL")

    def test_duplicate_symbol_case_insensitive(self):
        add_watchlist_item(self.db, self.wl_id, "AAPL")
        with self.assertRaises(ValueError):
            add_watchlist_item(self.db, self.wl_id, "aapl")

    def test_same_symbol_different_watchlists_allowed(self):
        wl2 = create_watchlist(self.db, "Secondary")
        add_watchlist_item(self.db, self.wl_id,    "AAPL")
        add_watchlist_item(self.db, wl2["id"], "AAPL")  # must not raise

    def test_universe_outside_symbol_allowed(self):
        r = add_watchlist_item(self.db, self.wl_id, "UNLISTED_CO")
        self.assertEqual(r["symbol"], "UNLISTED_CO")

    def test_nonexistent_watchlist_raises(self):
        with self.assertRaises(ValueError):
            add_watchlist_item(self.db, 99999, "AAPL")

    def test_include_archived_false_excludes_archived(self):
        add_watchlist_item(self.db, self.wl_id, "AAPL", status="archived")
        self.assertEqual(list_watchlist_items(self.db, self.wl_id, include_archived=False), [])

    def test_include_archived_true_returns_all(self):
        add_watchlist_item(self.db, self.wl_id, "AAPL", status="archived")
        self.assertEqual(len(list_watchlist_items(self.db, self.wl_id, include_archived=True)), 1)

    def test_fk_enforcement_at_db_level(self):
        """With foreign_keys=ON, inserting invalid watchlist_id should fail."""
        from ledger.db import get_connection as gc
        conn = gc(self.db)
        conn.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(Exception):
            conn.execute(
                "INSERT INTO watchlist_items (watchlist_id, symbol, added_at, updated_at)"
                " VALUES (99999, 'TEST', datetime('now'), datetime('now'))"
            )
        conn.close()


# ── update watchlist item ─────────────────────────────────────────────────────

class TestUpdateWatchlistItem(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        wl = create_watchlist(self.db, "Main")
        self.item = add_watchlist_item(self.db, wl["id"], "AAPL")

    def test_update_allowed_field(self):
        r = update_watchlist_item(self.db, self.item["id"], {"thesis_summary": "New thesis"})
        self.assertEqual(r["thesis_summary"], "New thesis")

    def test_update_status(self):
        r = update_watchlist_item(self.db, self.item["id"], {"status": "monitoring"})
        self.assertEqual(r["status"], "monitoring")

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            update_watchlist_item(self.db, self.item["id"], {"status": "invalid"})

    def test_unknown_fields_silently_ignored(self):
        r = update_watchlist_item(self.db, self.item["id"], {"symbol": "MSFT", "watchlist_id": 99})
        # symbol must not change
        self.assertEqual(r["symbol"], "AAPL")

    def test_updated_at_refreshed(self):
        conn = get_connection(self.db)
        conn.execute(
            "UPDATE watchlist_items SET updated_at = '2020-01-01 00:00:00' WHERE id = ?",
            (self.item["id"],),
        )
        conn.commit()
        conn.close()
        r = update_watchlist_item(self.db, self.item["id"], {"operation_focus": "Cloud"})
        self.assertGreater(r["updated_at"], "2020-01-01 00:00:00")

    def test_not_found_returns_none(self):
        r = update_watchlist_item(self.db, 99999, {"status": "archived"})
        self.assertIsNone(r)


# ── coverage check ────────────────────────────────────────────────────────────

class TestCoverage(unittest.TestCase):
    def setUp(self):
        self.lg, self.lg_db = _ledger_with_positions()   # 2 active positions
        init_watchlist_tables(self.lg_db)
        self.wl = create_watchlist(self.lg_db, "Main")
        self.wl_id = self.wl["id"]

    def test_coverage_keys(self):
        r = get_watchlist_coverage(self.lg_db, self.wl_id, self.lg)
        for k in ("watchlist_id", "watchlist_name", "active_position_count",
                  "required_watchlist_count", "current_active_item_count",
                  "coverage_sufficient", "gap"):
            self.assertIn(k, r)

    def test_empty_watchlist_insufficient(self):
        r = get_watchlist_coverage(self.lg_db, self.wl_id, self.lg)
        self.assertEqual(r["active_position_count"], 2)
        self.assertEqual(r["required_watchlist_count"], 6)
        self.assertEqual(r["current_active_item_count"], 0)
        self.assertFalse(r["coverage_sufficient"])
        self.assertEqual(r["gap"], 6)

    def test_exactly_3x_sufficient(self):
        for i in range(6):
            add_watchlist_item(self.lg_db, self.wl_id, f"SYM{i}")
        r = get_watchlist_coverage(self.lg_db, self.wl_id, self.lg)
        self.assertTrue(r["coverage_sufficient"])
        self.assertEqual(r["gap"], 0)

    def test_one_short_of_3x(self):
        for i in range(5):
            add_watchlist_item(self.lg_db, self.wl_id, f"SYM{i}")
        r = get_watchlist_coverage(self.lg_db, self.wl_id, self.lg)
        self.assertFalse(r["coverage_sufficient"])
        self.assertEqual(r["gap"], 1)

    def test_archived_items_not_counted(self):
        for i in range(6):
            add_watchlist_item(self.lg_db, self.wl_id, f"SYM{i}", status="archived")
        r = get_watchlist_coverage(self.lg_db, self.wl_id, self.lg)
        self.assertEqual(r["current_active_item_count"], 0)
        self.assertFalse(r["coverage_sufficient"])

    def test_no_active_positions_always_sufficient(self):
        lg, lg_db = _ledger_empty()
        init_watchlist_tables(lg_db)
        wl = create_watchlist(lg_db, "Empty")
        r = get_watchlist_coverage(lg_db, wl["id"], lg)
        self.assertEqual(r["active_position_count"], 0)
        self.assertEqual(r["required_watchlist_count"], 0)
        self.assertTrue(r["coverage_sufficient"])
        self.assertEqual(r["gap"], 0)

    def test_nonexistent_watchlist_raises(self):
        with self.assertRaises(ValueError):
            get_watchlist_coverage(self.lg_db, 99999, self.lg)


# ── gap analysis ──────────────────────────────────────────────────────────────

class TestGaps(unittest.TestCase):
    def setUp(self):
        self.lg, self.lg_db = _ledger_with_positions()   # AAPL + TSLA
        init_watchlist_tables(self.lg_db)
        self.wl = create_watchlist(self.lg_db, "Main")
        self.wl_id = self.wl["id"]

    def test_gap_contract_keys(self):
        r = list_watchlist_gaps(self.lg_db, self.wl_id, self.lg)
        for k in ("watchlist_id", "watchlist_name", "active_position_count",
                  "required_watchlist_count", "current_active_item_count",
                  "coverage_sufficient", "gap",
                  "positions_not_in_watchlist", "positions_in_watchlist"):
            self.assertIn(k, r)

    def test_positions_not_in_watchlist_when_empty(self):
        r = list_watchlist_gaps(self.lg_db, self.wl_id, self.lg)
        self.assertIn("AAPL", r["positions_not_in_watchlist"])
        self.assertIn("TSLA", r["positions_not_in_watchlist"])
        self.assertEqual(r["positions_in_watchlist"], [])

    def test_positions_move_to_in_watchlist_after_add(self):
        add_watchlist_item(self.lg_db, self.wl_id, "AAPL")
        r = list_watchlist_gaps(self.lg_db, self.wl_id, self.lg)
        self.assertIn("AAPL", r["positions_in_watchlist"])
        self.assertNotIn("AAPL", r["positions_not_in_watchlist"])
        self.assertIn("TSLA", r["positions_not_in_watchlist"])

    def test_non_position_watchlist_items_not_in_gap_lists(self):
        # Adding a symbol that is NOT a position should not appear in gap lists
        add_watchlist_item(self.lg_db, self.wl_id, "MSFT")
        r = list_watchlist_gaps(self.lg_db, self.wl_id, self.lg)
        self.assertNotIn("MSFT", r["positions_not_in_watchlist"])
        self.assertNotIn("MSFT", r["positions_in_watchlist"])

    def test_no_positions_empty_gap_lists(self):
        lg, lg_db = _ledger_empty()
        init_watchlist_tables(lg_db)
        wl = create_watchlist(lg_db, "Empty")
        r = list_watchlist_gaps(lg_db, wl["id"], lg)
        self.assertEqual(r["positions_not_in_watchlist"], [])
        self.assertEqual(r["positions_in_watchlist"], [])

    def test_coverage_summary_fields_match_coverage_endpoint(self):
        cov = get_watchlist_coverage(self.lg_db, self.wl_id, self.lg)
        gaps = list_watchlist_gaps(self.lg_db, self.wl_id, self.lg)
        for k in ("active_position_count", "required_watchlist_count",
                  "current_active_item_count", "coverage_sufficient", "gap"):
            self.assertEqual(cov[k], gaps[k])


if __name__ == "__main__":
    unittest.main()
