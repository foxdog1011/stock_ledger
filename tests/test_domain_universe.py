"""Tests for domain.universe repository and service."""
import tempfile
import unittest
from pathlib import Path

from ledger import StockLedger
from domain.universe.repository import (
    init_universe_tables,
    add_company,
    get_company,
    list_companies,
    update_company,
    add_relationship,
    list_relationships,
    add_thesis,
    list_thesis,
    deactivate_thesis,
)
from domain.universe.service import get_company_detail
from ledger.db import get_connection


def _db() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    p = Path(tmp.name)
    init_universe_tables(p)
    return p


# ── init idempotency ──────────────────────────────────────────────────────────

class TestInitIdempotent(unittest.TestCase):
    def test_double_init_no_error(self):
        db = _db()
        init_universe_tables(db)  # second call must not raise


# ── company master ────────────────────────────────────────────────────────────

class TestAddCompany(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_add_and_get(self):
        add_company(self.db, "AAPL", "Apple Inc.", sector="Technology")
        r = get_company(self.db, "AAPL")
        self.assertIsNotNone(r)
        self.assertEqual(r["symbol"], "AAPL")
        self.assertEqual(r["name"], "Apple Inc.")
        self.assertEqual(r["sector"], "Technology")

    def test_symbol_normalised(self):
        add_company(self.db, " aapl ", "Apple")
        r = get_company(self.db, "aapl")
        self.assertEqual(r["symbol"], "AAPL")

    def test_duplicate_symbol_raises(self):
        add_company(self.db, "AAPL", "Apple")
        with self.assertRaises(ValueError):
            add_company(self.db, "AAPL", "Apple Duplicate")

    def test_duplicate_symbol_case_insensitive(self):
        add_company(self.db, "AAPL", "Apple")
        with self.assertRaises(ValueError):
            add_company(self.db, "aapl", "Apple lowercase")

    def test_created_at_and_updated_at_set(self):
        r = add_company(self.db, "AAPL", "Apple")
        self.assertIsNotNone(r["created_at"])
        self.assertIsNotNone(r["updated_at"])
        # datetime format: YYYY-MM-DD HH:MM:SS
        self.assertRegex(r["created_at"], r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_optional_fields_default_none(self):
        r = add_company(self.db, "AAPL", "Apple")
        for field in ("exchange", "sector", "industry", "business_model",
                      "country", "currency"):
            self.assertIsNone(r[field])

    def test_note_default_empty_string(self):
        r = add_company(self.db, "AAPL", "Apple")
        self.assertEqual(r["note"], "")


class TestGetCompany(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_not_found_returns_none(self):
        self.assertIsNone(get_company(self.db, "ZZZZ"))

    def test_get_normalises_symbol(self):
        add_company(self.db, "AAPL", "Apple")
        self.assertIsNotNone(get_company(self.db, " aapl "))


class TestListCompanies(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_empty_returns_empty_list(self):
        self.assertEqual(list_companies(self.db), [])

    def test_sorted_by_symbol(self):
        add_company(self.db, "TSMC", "TSMC")
        add_company(self.db, "AAPL", "Apple")
        symbols = [r["symbol"] for r in list_companies(self.db)]
        self.assertEqual(symbols, sorted(symbols))


class TestUpdateCompany(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        add_company(self.db, "AAPL", "Apple Inc.")

    def test_update_field(self):
        r = update_company(self.db, "AAPL", {"sector": "Technology"})
        self.assertEqual(r["sector"], "Technology")

    def test_updated_at_refreshed(self):
        # Force updated_at to a known-old value
        conn = get_connection(self.db)
        conn.execute(
            "UPDATE company_master SET updated_at = '2020-01-01 00:00:00' WHERE symbol = 'AAPL'"
        )
        conn.commit()
        conn.close()
        update_company(self.db, "AAPL", {"sector": "Technology"})
        r = get_company(self.db, "AAPL")
        self.assertGreater(r["updated_at"], "2020-01-01 00:00:00")

    def test_unknown_fields_silently_ignored(self):
        r = update_company(self.db, "AAPL", {"nonexistent_field": "value"})
        self.assertIsNotNone(r)

    def test_not_found_returns_none(self):
        r = update_company(self.db, "ZZZZ", {"sector": "X"})
        self.assertIsNone(r)

    def test_symbol_normalised(self):
        r = update_company(self.db, " aapl ", {"sector": "Tech"})
        self.assertIsNotNone(r)
        self.assertEqual(r["sector"], "Tech")

    def test_created_at_unchanged_after_update(self):
        before = get_company(self.db, "AAPL")
        update_company(self.db, "AAPL", {"sector": "Tech"})
        after = get_company(self.db, "AAPL")
        self.assertEqual(before["created_at"], after["created_at"])


# ── relationships ─────────────────────────────────────────────────────────────

class TestRelationships(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        add_company(self.db, "AAPL", "Apple Inc.")

    def test_add_and_list(self):
        add_relationship(self.db, "AAPL", "MSFT", "competitor")
        rows = list_relationships(self.db, "AAPL")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["related_symbol"], "MSFT")
        self.assertEqual(rows[0]["relationship_type"], "competitor")

    def test_symbol_and_related_normalised(self):
        add_relationship(self.db, " aapl ", " msft ", "competitor")
        rows = list_relationships(self.db, "AAPL")
        self.assertEqual(rows[0]["symbol"], "AAPL")
        self.assertEqual(rows[0]["related_symbol"], "MSFT")

    def test_invalid_relationship_type_raises(self):
        with self.assertRaises(ValueError):
            add_relationship(self.db, "AAPL", "MSFT", "rival")

    def test_all_valid_relationship_types(self):
        for i, rel_type in enumerate(["competitor", "supplier", "customer", "partner"]):
            add_relationship(self.db, "AAPL", f"CO{i}", rel_type)
        self.assertEqual(len(list_relationships(self.db, "AAPL")), 4)

    def test_duplicate_raises(self):
        add_relationship(self.db, "AAPL", "MSFT", "competitor")
        with self.assertRaises(ValueError):
            add_relationship(self.db, "AAPL", "MSFT", "competitor")

    def test_related_symbol_not_in_master_allowed(self):
        # related_symbol does not need to be in company_master
        r = add_relationship(self.db, "AAPL", "UNLISTED_CO", "supplier")
        self.assertEqual(r["related_symbol"], "UNLISTED_CO")

    def test_symbol_not_in_master_raises(self):
        with self.assertRaises(ValueError):
            add_relationship(self.db, "ZZZZ", "AAPL", "competitor")

    def test_list_empty_for_unknown_symbol(self):
        self.assertEqual(list_relationships(self.db, "ZZZZ"), [])

    def test_sorted_by_type_then_related(self):
        add_relationship(self.db, "AAPL", "Z_CO", "competitor")
        add_relationship(self.db, "AAPL", "A_CO", "competitor")
        rows = list_relationships(self.db, "AAPL")
        related = [r["related_symbol"] for r in rows]
        self.assertEqual(related, sorted(related))


# ── thesis ────────────────────────────────────────────────────────────────────

class TestThesis(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        add_company(self.db, "AAPL", "Apple Inc.")

    def test_add_and_list_active(self):
        add_thesis(self.db, "AAPL", "bull", "Strong iPhone supercycle")
        rows = list_thesis(self.db, "AAPL", active_only=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["thesis_type"], "bull")
        self.assertEqual(rows[0]["is_active"], 1)

    def test_symbol_normalised(self):
        add_thesis(self.db, " aapl ", "bull", "content")
        rows = list_thesis(self.db, "AAPL")
        self.assertEqual(rows[0]["symbol"], "AAPL")

    def test_invalid_thesis_type_raises(self):
        with self.assertRaises(ValueError):
            add_thesis(self.db, "AAPL", "neutral", "content")

    def test_all_valid_thesis_types(self):
        for t in ["bull", "bear", "operation_focus", "risk_factor"]:
            add_thesis(self.db, "AAPL", t, f"content for {t}")
        self.assertEqual(len(list_thesis(self.db, "AAPL")), 4)

    def test_symbol_not_in_master_raises(self):
        with self.assertRaises(ValueError):
            add_thesis(self.db, "ZZZZ", "bull", "content")

    def test_list_empty_for_unknown_symbol(self):
        self.assertEqual(list_thesis(self.db, "ZZZZ"), [])

    def test_active_only_false_includes_inactive(self):
        r = add_thesis(self.db, "AAPL", "bull", "content")
        deactivate_thesis(self.db, r["id"])
        self.assertEqual(list_thesis(self.db, "AAPL", active_only=True), [])
        self.assertEqual(len(list_thesis(self.db, "AAPL", active_only=False)), 1)

    def test_deactivate_sets_is_active_zero(self):
        r = add_thesis(self.db, "AAPL", "bull", "content")
        deactivate_thesis(self.db, r["id"])
        rows = list_thesis(self.db, "AAPL", active_only=False)
        self.assertEqual(rows[0]["is_active"], 0)

    def test_deactivate_not_found_raises(self):
        with self.assertRaises(ValueError):
            deactivate_thesis(self.db, 99999)

    def test_deactivate_already_inactive_raises(self):
        r = add_thesis(self.db, "AAPL", "bull", "content")
        deactivate_thesis(self.db, r["id"])
        with self.assertRaises(ValueError):
            deactivate_thesis(self.db, r["id"])


# ── service: get_company_detail ───────────────────────────────────────────────

class TestGetCompanyDetail(unittest.TestCase):
    def setUp(self):
        self.db = _db()
        add_company(self.db, "AAPL", "Apple Inc.", sector="Technology")
        add_relationship(self.db, "AAPL", "MSFT", "competitor")
        add_thesis(self.db, "AAPL", "bull", "AI tailwinds")

    def test_returns_none_for_unknown(self):
        self.assertIsNone(get_company_detail(self.db, "ZZZZ"))

    def test_contains_master_fields(self):
        r = get_company_detail(self.db, "AAPL")
        self.assertEqual(r["symbol"], "AAPL")
        self.assertEqual(r["sector"], "Technology")

    def test_contains_relationships(self):
        r = get_company_detail(self.db, "AAPL")
        self.assertEqual(len(r["relationships"]), 1)
        self.assertEqual(r["relationships"][0]["related_symbol"], "MSFT")

    def test_contains_active_thesis_only(self):
        r = get_company_detail(self.db, "AAPL")
        self.assertEqual(len(r["thesis"]), 1)
        self.assertEqual(r["thesis"][0]["thesis_type"], "bull")

    def test_segments_is_empty_list(self):
        r = get_company_detail(self.db, "AAPL")
        self.assertEqual(r["segments"], [])

    def test_deactivated_thesis_excluded(self):
        rows = list_thesis(self.db, "AAPL")
        deactivate_thesis(self.db, rows[0]["id"])
        r = get_company_detail(self.db, "AAPL")
        self.assertEqual(r["thesis"], [])


if __name__ == "__main__":
    unittest.main()
