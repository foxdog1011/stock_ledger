"""Tests for domain.catalyst and domain.scenario repositories and services."""
import tempfile
import unittest
from pathlib import Path

from domain.catalyst.repository import (
    init_catalyst_tables,
    create_catalyst,
    get_catalyst,
    list_catalysts,
    update_catalyst,
)
from domain.catalyst.service import upcoming_catalysts
from domain.scenario.repository import (
    init_scenario_tables,
    upsert_scenario,
    get_scenario,
    UPDATABLE_SCENARIO_FIELDS,
)


def _db() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    p = Path(tmp.name)
    init_catalyst_tables(p)
    init_scenario_tables(p)
    return p


# ── init idempotency ──────────────────────────────────────────────────────────

class TestInit(unittest.TestCase):
    def test_double_init_no_error(self):
        db = _db()
        init_catalyst_tables(db)
        init_scenario_tables(db)


# ── create catalyst ───────────────────────────────────────────────────────────

class TestCreateCatalyst(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_company_event_with_symbol(self):
        r = create_catalyst(self.db, "company", "Earnings Q1", symbol="AAPL")
        self.assertEqual(r["event_type"], "company")
        self.assertEqual(r["symbol"], "AAPL")
        self.assertEqual(r["title"], "Earnings Q1")
        self.assertEqual(r["status"], "pending")

    def test_macro_event_without_symbol(self):
        r = create_catalyst(self.db, "macro", "Fed rate decision", symbol=None)
        self.assertEqual(r["event_type"], "macro")
        self.assertIsNone(r["symbol"])

    def test_sector_event(self):
        r = create_catalyst(self.db, "sector", "Semiconductor supply update")
        self.assertEqual(r["event_type"], "sector")

    def test_invalid_event_type_raises(self):
        with self.assertRaises(ValueError):
            create_catalyst(self.db, "invalid", "Bad type")

    def test_event_date_none_allowed(self):
        r = create_catalyst(self.db, "macro", "TBD event", event_date=None)
        self.assertIsNone(r["event_date"])

    def test_event_date_stored(self):
        r = create_catalyst(self.db, "company", "Earnings", event_date="2025-04-15")
        self.assertEqual(r["event_date"], "2025-04-15")

    def test_symbol_normalised(self):
        r = create_catalyst(self.db, "company", "Earnings", symbol=" aapl ")
        self.assertEqual(r["symbol"], "AAPL")

    def test_id_assigned(self):
        r = create_catalyst(self.db, "macro", "Test")
        self.assertIsNotNone(r["id"])

    def test_timestamps_set(self):
        r = create_catalyst(self.db, "macro", "Test")
        self.assertRegex(r["created_at"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.assertRegex(r["updated_at"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


# ── get catalyst ──────────────────────────────────────────────────────────────

class TestGetCatalyst(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_get_existing(self):
        c = create_catalyst(self.db, "macro", "Rate hike")
        r = get_catalyst(self.db, c["id"])
        self.assertEqual(r["id"], c["id"])

    def test_get_not_found_returns_none(self):
        self.assertIsNone(get_catalyst(self.db, 99999))


# ── list catalysts ────────────────────────────────────────────────────────────

class TestListCatalysts(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        create_catalyst(self.db, "company", "AAPL Earnings", symbol="AAPL",
                        event_date="2025-04-15")
        create_catalyst(self.db, "macro", "Fed decision", event_date="2025-05-01")
        c3 = create_catalyst(self.db, "company", "TSLA delivery", symbol="TSLA",
                             event_date="2025-04-20")
        update_catalyst(self.db, c3["id"], {"status": "passed"})

    def test_list_all(self):
        self.assertEqual(len(list_catalysts(self.db)), 3)

    def test_filter_by_symbol(self):
        r = list_catalysts(self.db, symbol="AAPL")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["symbol"], "AAPL")

    def test_filter_by_symbol_normalised(self):
        r = list_catalysts(self.db, symbol=" aapl ")
        self.assertEqual(len(r), 1)

    def test_filter_by_status_pending(self):
        r = list_catalysts(self.db, status="pending")
        self.assertEqual(len(r), 2)

    def test_filter_by_status_passed(self):
        r = list_catalysts(self.db, status="passed")
        self.assertEqual(len(r), 1)

    def test_filter_by_event_type(self):
        r = list_catalysts(self.db, event_type="macro")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["event_type"], "macro")

    def test_invalid_status_filter_raises(self):
        with self.assertRaises(ValueError):
            list_catalysts(self.db, status="bad_status")

    def test_invalid_event_type_filter_raises(self):
        with self.assertRaises(ValueError):
            list_catalysts(self.db, event_type="unknown")

    def test_sorted_by_event_date_asc(self):
        rows = list_catalysts(self.db, status="pending")
        dates = [r["event_date"] for r in rows if r["event_date"]]
        self.assertEqual(dates, sorted(dates))


# ── update catalyst ───────────────────────────────────────────────────────────

class TestUpdateCatalyst(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        self.cat = create_catalyst(self.db, "company", "Earnings", symbol="AAPL")

    def test_update_status(self):
        r = update_catalyst(self.db, self.cat["id"], {"status": "passed"})
        self.assertEqual(r["status"], "passed")

    def test_update_title(self):
        r = update_catalyst(self.db, self.cat["id"], {"title": "New title"})
        self.assertEqual(r["title"], "New title")

    def test_update_event_date(self):
        r = update_catalyst(self.db, self.cat["id"], {"event_date": "2025-06-01"})
        self.assertEqual(r["event_date"], "2025-06-01")

    def test_update_notes(self):
        r = update_catalyst(self.db, self.cat["id"], {"notes": "Revised thesis"})
        self.assertEqual(r["notes"], "Revised thesis")

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            update_catalyst(self.db, self.cat["id"], {"status": "bad"})

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            update_catalyst(self.db, self.cat["id"], {"symbol": "MSFT"})

    def test_unknown_field_raises_even_with_valid_fields(self):
        with self.assertRaises(ValueError):
            update_catalyst(self.db, self.cat["id"], {"status": "passed", "bogus": "x"})

    def test_not_found_returns_none(self):
        r = update_catalyst(self.db, 99999, {"status": "passed"})
        self.assertIsNone(r)

    def test_updated_at_refreshed(self):
        from ledger.db import get_connection
        conn = get_connection(self.db)
        conn.execute(
            "UPDATE catalysts SET updated_at = '2020-01-01 00:00:00' WHERE id = ?",
            (self.cat["id"],),
        )
        conn.commit()
        conn.close()
        r = update_catalyst(self.db, self.cat["id"], {"notes": "bump"})
        self.assertGreater(r["updated_at"], "2020-01-01 00:00:00")


# ── scenario upsert ───────────────────────────────────────────────────────────

class TestScenario(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        self.cat = create_catalyst(self.db, "company", "Earnings", symbol="AAPL")
        self.cat_id = self.cat["id"]

    def test_first_upsert_creates(self):
        r = upsert_scenario(self.db, self.cat_id, {"plan_a": "Buy more"})
        self.assertEqual(r["plan_a"], "Buy more")
        self.assertIsNotNone(r["id"])

    def test_second_upsert_partial_update(self):
        upsert_scenario(self.db, self.cat_id, {"plan_a": "Buy more", "plan_b": "Hold"})
        r = upsert_scenario(self.db, self.cat_id, {"plan_a": "Revised"})
        self.assertEqual(r["plan_a"], "Revised")
        self.assertEqual(r["plan_b"], "Hold")  # unchanged

    def test_all_plan_fields_stored(self):
        r = upsert_scenario(self.db, self.cat_id, {
            "plan_a": "A", "plan_b": "B", "plan_c": "C", "plan_d": "D",
        })
        for k, v in [("plan_a", "A"), ("plan_b", "B"), ("plan_c", "C"), ("plan_d", "D")]:
            self.assertEqual(r[k], v)

    def test_price_target_stored(self):
        r = upsert_scenario(self.db, self.cat_id, {"price_target": 200.0})
        self.assertAlmostEqual(r["price_target"], 200.0)

    def test_stop_loss_stored(self):
        r = upsert_scenario(self.db, self.cat_id, {"stop_loss": 150.0})
        self.assertAlmostEqual(r["stop_loss"], 150.0)

    def test_price_target_none_allowed(self):
        r = upsert_scenario(self.db, self.cat_id, {})
        self.assertIsNone(r["price_target"])

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            upsert_scenario(self.db, self.cat_id, {"bull_case": "bad field"})

    def test_nonexistent_catalyst_raises(self):
        with self.assertRaises(ValueError):
            upsert_scenario(self.db, 99999, {"plan_a": "x"})

    def test_get_scenario_existing(self):
        upsert_scenario(self.db, self.cat_id, {"plan_a": "Go long"})
        r = get_scenario(self.db, self.cat_id)
        self.assertIsNotNone(r)
        self.assertEqual(r["plan_a"], "Go long")

    def test_get_scenario_not_found_returns_none(self):
        self.assertIsNone(get_scenario(self.db, self.cat_id))

    def test_updated_at_refreshed_on_second_upsert(self):
        upsert_scenario(self.db, self.cat_id, {"plan_a": "v1"})
        from ledger.db import get_connection
        conn = get_connection(self.db)
        conn.execute(
            "UPDATE scenario_plans SET updated_at = '2020-01-01 00:00:00' WHERE catalyst_id = ?",
            (self.cat_id,),
        )
        conn.commit()
        conn.close()
        r = upsert_scenario(self.db, self.cat_id, {"plan_b": "v2"})
        self.assertGreater(r["updated_at"], "2020-01-01 00:00:00")

    def test_unique_one_scenario_per_catalyst(self):
        upsert_scenario(self.db, self.cat_id, {"plan_a": "v1"})
        upsert_scenario(self.db, self.cat_id, {"plan_a": "v2"})
        from ledger.db import get_connection
        conn = get_connection(self.db)
        count = conn.execute(
            "SELECT COUNT(*) FROM scenario_plans WHERE catalyst_id = ?",
            (self.cat_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_scenario_deleted_with_catalyst(self):
        upsert_scenario(self.db, self.cat_id, {"plan_a": "x"})
        from ledger.db import get_connection
        conn = get_connection(self.db)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM catalysts WHERE id = ?", (self.cat_id,))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM scenario_plans WHERE catalyst_id = ?", (self.cat_id,)
        ).fetchone()
        conn.close()
        self.assertIsNone(row)


# ── upcoming catalysts ────────────────────────────────────────────────────────

class TestUpcomingCatalysts(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_empty_returns_empty_list(self):
        self.assertEqual(upcoming_catalysts(self.db, as_of="2025-04-01"), [])

    def test_event_within_range_appears(self):
        create_catalyst(self.db, "company", "Earnings", event_date="2025-04-10")
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["event_date"], "2025-04-10")

    def test_event_outside_range_excluded(self):
        create_catalyst(self.db, "company", "Far future", event_date="2025-06-01")
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(r, [])

    def test_event_date_none_excluded(self):
        create_catalyst(self.db, "macro", "Unknown date", event_date=None)
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(r, [])

    def test_passed_catalyst_excluded(self):
        c = create_catalyst(self.db, "company", "Done", event_date="2025-04-10")
        update_catalyst(self.db, c["id"], {"status": "passed"})
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(r, [])

    def test_cancelled_catalyst_excluded(self):
        c = create_catalyst(self.db, "company", "Cancelled", event_date="2025-04-10")
        update_catalyst(self.db, c["id"], {"status": "cancelled"})
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(r, [])

    def test_sorted_by_event_date_asc(self):
        create_catalyst(self.db, "company", "Late",  event_date="2025-04-25")
        create_catalyst(self.db, "company", "Early", event_date="2025-04-05")
        create_catalyst(self.db, "macro",   "Mid",   event_date="2025-04-15")
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        dates = [x["event_date"] for x in r]
        self.assertEqual(dates, sorted(dates))

    def test_scenario_included_when_present(self):
        c = create_catalyst(self.db, "company", "Earnings", event_date="2025-04-10")
        upsert_scenario(self.db, c["id"], {"plan_a": "Go long"})
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertIsNotNone(r[0]["scenario"])
        self.assertEqual(r[0]["scenario"]["plan_a"], "Go long")

    def test_scenario_none_when_absent(self):
        create_catalyst(self.db, "company", "Earnings", event_date="2025-04-10")
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertIsNone(r[0]["scenario"])

    def test_boundary_as_of_date_inclusive(self):
        create_catalyst(self.db, "company", "Same day", event_date="2025-04-01")
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(len(r), 1)

    def test_boundary_end_date_inclusive(self):
        create_catalyst(self.db, "company", "Last day", event_date="2025-05-01")
        r = upcoming_catalysts(self.db, as_of="2025-04-01", days=30)
        self.assertEqual(len(r), 1)


if __name__ == "__main__":
    unittest.main()
