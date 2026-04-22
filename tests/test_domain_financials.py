"""Tests for domain.financials: models (constants) and repository (SQL operations)."""
import tempfile
import unittest
from pathlib import Path

from domain.financials.models import (
    BALANCE_FIELDS,
    CASHFLOW_FIELDS,
    INCOME_FIELDS,
    STATEMENT_TYPES,
)
from domain.financials.repository import (
    get_dividend_history,
    get_financial_statements,
    get_tdcc_distribution,
    get_valuation_metrics,
    init_financials_tables,
    store_dividend_rows,
    store_financial_rows,
    store_tdcc_rows,
    store_valuation_rows,
)


def _db() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    p = Path(tmp.name)
    init_financials_tables(p)
    return p


# ── Constants (models.py) ────────────────────────────────────────────────────


class TestConstants(unittest.TestCase):
    def test_statement_types(self):
        self.assertEqual(STATEMENT_TYPES, {"income", "balance", "cashflow"})

    def test_statement_types_is_frozenset(self):
        self.assertIsInstance(STATEMENT_TYPES, frozenset)

    def test_income_fields_not_empty(self):
        self.assertTrue(len(INCOME_FIELDS) > 0)
        self.assertIn("revenue", INCOME_FIELDS)
        self.assertIn("eps", INCOME_FIELDS)

    def test_balance_fields_not_empty(self):
        self.assertTrue(len(BALANCE_FIELDS) > 0)
        self.assertIn("total_assets", BALANCE_FIELDS)
        self.assertIn("equity", BALANCE_FIELDS)

    def test_cashflow_fields_not_empty(self):
        self.assertTrue(len(CASHFLOW_FIELDS) > 0)
        self.assertIn("free_cashflow", CASHFLOW_FIELDS)
        self.assertIn("capex", CASHFLOW_FIELDS)

    def test_all_field_sets_are_frozenset(self):
        self.assertIsInstance(INCOME_FIELDS, frozenset)
        self.assertIsInstance(BALANCE_FIELDS, frozenset)
        self.assertIsInstance(CASHFLOW_FIELDS, frozenset)


# ── Table initialisation ─────────────────────────────────────────────────────


class TestInitTables(unittest.TestCase):
    def test_init_creates_tables(self):
        db = _db()
        from ledger.db import get_connection

        conn = get_connection(db)
        try:
            tables = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        self.assertIn("financial_statements", tables)
        self.assertIn("valuation_metrics", tables)
        self.assertIn("dividend_history", tables)
        self.assertIn("tdcc_distribution", tables)

    def test_idempotent_init(self):
        db = _db()
        init_financials_tables(db)
        init_financials_tables(db)  # should not raise


# ── Financial Statements ─────────────────────────────────────────────────────


class TestFinancialStatements(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_store_and_retrieve(self):
        rows = [
            {"date": "2025-Q1", "origin_name": "revenue", "value": 100.5},
            {"date": "2025-Q1", "origin_name": "net_income", "value": 20.3},
            {"date": "2024-Q4", "origin_name": "revenue", "value": 95.0},
        ]
        count = store_financial_rows(self.db, "2330", "income", rows)
        self.assertEqual(count, 3)

        result = get_financial_statements(self.db, "2330", "income")
        self.assertEqual(len(result), 2)  # 2 dates
        # Ordered by date DESC => 2025-Q1 first
        self.assertEqual(result[0]["date"], "2025-Q1")
        self.assertEqual(result[0]["revenue"], 100.5)
        self.assertEqual(result[0]["net_income"], 20.3)
        self.assertEqual(result[1]["date"], "2024-Q4")

    def test_symbol_normalised_to_uppercase(self):
        rows = [{"date": "2025-Q1", "origin_name": "eps", "value": 5.0}]
        store_financial_rows(self.db, " tsmc ", "income", rows)
        result = get_financial_statements(self.db, "TSMC", "income")
        self.assertEqual(len(result), 1)

    def test_skip_rows_missing_date(self):
        rows = [
            {"date": "", "origin_name": "revenue", "value": 100},
            {"origin_name": "revenue", "value": 200},  # no date key at all
        ]
        count = store_financial_rows(self.db, "2330", "income", rows)
        self.assertEqual(count, 0)

    def test_skip_rows_missing_origin(self):
        rows = [{"date": "2025-Q1", "value": 100}]  # no origin_name or type
        count = store_financial_rows(self.db, "2330", "income", rows)
        self.assertEqual(count, 0)

    def test_fallback_to_type_key_for_origin(self):
        rows = [{"date": "2025-Q1", "type": "revenue", "value": 42}]
        count = store_financial_rows(self.db, "2330", "income", rows)
        self.assertEqual(count, 1)
        result = get_financial_statements(self.db, "2330", "income")
        self.assertIn("revenue", result[0])

    def test_upsert_replaces_existing(self):
        rows = [{"date": "2025-Q1", "origin_name": "revenue", "value": 100}]
        store_financial_rows(self.db, "2330", "income", rows)
        rows2 = [{"date": "2025-Q1", "origin_name": "revenue", "value": 999}]
        store_financial_rows(self.db, "2330", "income", rows2)
        result = get_financial_statements(self.db, "2330", "income")
        self.assertEqual(result[0]["revenue"], 999)

    def test_limit_parameter(self):
        for i in range(5):
            rows = [{"date": f"2025-Q{i}", "origin_name": "eps", "value": i}]
            store_financial_rows(self.db, "2330", "income", rows)
        result = get_financial_statements(self.db, "2330", "income", limit=3)
        self.assertEqual(len(result), 3)

    def test_empty_result(self):
        result = get_financial_statements(self.db, "NONE", "income")
        self.assertEqual(result, [])

    def test_different_stmt_types_isolated(self):
        store_financial_rows(
            self.db, "2330", "income",
            [{"date": "2025-Q1", "origin_name": "revenue", "value": 100}],
        )
        store_financial_rows(
            self.db, "2330", "balance",
            [{"date": "2025-Q1", "origin_name": "total_assets", "value": 500}],
        )
        income = get_financial_statements(self.db, "2330", "income")
        balance = get_financial_statements(self.db, "2330", "balance")
        self.assertEqual(len(income), 1)
        self.assertIn("revenue", income[0])
        self.assertNotIn("total_assets", income[0])
        self.assertEqual(len(balance), 1)
        self.assertIn("total_assets", balance[0])

    def test_null_value_stored(self):
        rows = [{"date": "2025-Q1", "origin_name": "eps", "value": None}]
        count = store_financial_rows(self.db, "2330", "income", rows)
        self.assertEqual(count, 1)
        result = get_financial_statements(self.db, "2330", "income")
        self.assertIsNone(result[0]["eps"])


# ── Valuation Metrics ────────────────────────────────────────────────────────


class TestValuationMetrics(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_store_and_retrieve(self):
        rows = [
            {"date": "2025-01-15", "PER": 15.2, "PBR": 3.1, "DividendYield": 2.5},
            {"date": "2025-01-14", "PER": 14.8, "PBR": 3.0, "DividendYield": 2.6},
        ]
        count = store_valuation_rows(self.db, "2330", rows)
        self.assertEqual(count, 2)

        result = get_valuation_metrics(self.db, "2330")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["date"], "2025-01-15")
        self.assertAlmostEqual(result[0]["per"], 15.2)
        self.assertAlmostEqual(result[0]["pbr"], 3.1)
        self.assertAlmostEqual(result[0]["dividend_yield"], 2.5)

    def test_lowercase_keys(self):
        rows = [{"date": "2025-01-15", "per": 10.0, "pbr": 2.0, "dividend_yield": 3.0}]
        count = store_valuation_rows(self.db, "2330", rows)
        self.assertEqual(count, 1)
        result = get_valuation_metrics(self.db, "2330")
        self.assertAlmostEqual(result[0]["per"], 10.0)
        self.assertAlmostEqual(result[0]["pbr"], 2.0)
        self.assertAlmostEqual(result[0]["dividend_yield"], 3.0)

    def test_skip_rows_missing_date(self):
        rows = [{"date": "", "PER": 10}]
        count = store_valuation_rows(self.db, "2330", rows)
        self.assertEqual(count, 0)

    def test_upsert_replaces_existing(self):
        rows = [{"date": "2025-01-15", "PER": 10}]
        store_valuation_rows(self.db, "2330", rows)
        rows2 = [{"date": "2025-01-15", "PER": 20}]
        store_valuation_rows(self.db, "2330", rows2)
        result = get_valuation_metrics(self.db, "2330")
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["per"], 20.0)

    def test_limit_parameter(self):
        for i in range(10):
            store_valuation_rows(
                self.db, "2330",
                [{"date": f"2025-01-{i+1:02d}", "PER": float(i)}],
            )
        result = get_valuation_metrics(self.db, "2330", limit=5)
        self.assertEqual(len(result), 5)

    def test_empty_result(self):
        result = get_valuation_metrics(self.db, "NONE")
        self.assertEqual(result, [])

    def test_symbol_normalised(self):
        store_valuation_rows(self.db, " tsmc ", [{"date": "2025-01-01", "PER": 5}])
        result = get_valuation_metrics(self.db, "TSMC")
        self.assertEqual(len(result), 1)

    def test_partial_fields(self):
        """Store a row with only PER, PBR and dividend_yield should be None."""
        rows = [{"date": "2025-01-15", "PER": 12.5}]
        store_valuation_rows(self.db, "2330", rows)
        result = get_valuation_metrics(self.db, "2330")
        self.assertAlmostEqual(result[0]["per"], 12.5)
        self.assertIsNone(result[0]["pbr"])
        self.assertIsNone(result[0]["dividend_yield"])


# ── Dividend History ─────────────────────────────────────────────────────────


class TestDividendHistory(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_store_and_retrieve_finmind_keys(self):
        rows = [
            {
                "date": "2025-06-15",
                "CashEarningsDistribution": 3.0,
                "StockEarningsDistribution": 0.5,
            },
        ]
        count = store_dividend_rows(self.db, "2330", rows)
        self.assertEqual(count, 1)
        result = get_dividend_history(self.db, "2330")
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["cash_dividend"], 3.0)
        self.assertAlmostEqual(result[0]["stock_dividend"], 0.5)

    def test_store_with_lowercase_keys(self):
        rows = [{"date": "2025-06-15", "cash_dividend": 2.0, "stock_dividend": 0.0}]
        count = store_dividend_rows(self.db, "2330", rows)
        self.assertEqual(count, 1)
        result = get_dividend_history(self.db, "2330")
        self.assertAlmostEqual(result[0]["cash_dividend"], 2.0)
        self.assertAlmostEqual(result[0]["stock_dividend"], 0.0)

    def test_skip_rows_missing_date(self):
        rows = [{"date": "", "cash_dividend": 1.0}]
        count = store_dividend_rows(self.db, "2330", rows)
        self.assertEqual(count, 0)

    def test_upsert_replaces(self):
        store_dividend_rows(self.db, "2330", [{"date": "2025-06-15", "cash_dividend": 1.0}])
        store_dividend_rows(self.db, "2330", [{"date": "2025-06-15", "cash_dividend": 5.0}])
        result = get_dividend_history(self.db, "2330")
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["cash_dividend"], 5.0)

    def test_limit_parameter(self):
        for i in range(5):
            store_dividend_rows(
                self.db, "2330",
                [{"date": f"2025-0{i+1}-15", "cash_dividend": float(i)}],
            )
        result = get_dividend_history(self.db, "2330", limit=3)
        self.assertEqual(len(result), 3)

    def test_ordered_by_date_desc(self):
        store_dividend_rows(self.db, "2330", [
            {"date": "2024-06-15", "cash_dividend": 1.0},
            {"date": "2025-06-15", "cash_dividend": 2.0},
            {"date": "2023-06-15", "cash_dividend": 0.5},
        ])
        result = get_dividend_history(self.db, "2330")
        dates = [r["date"] for r in result]
        self.assertEqual(dates, ["2025-06-15", "2024-06-15", "2023-06-15"])

    def test_empty_result(self):
        self.assertEqual(get_dividend_history(self.db, "NONE"), [])

    def test_symbol_normalised(self):
        store_dividend_rows(self.db, " tsmc ", [{"date": "2025-01-01", "cash_dividend": 1}])
        result = get_dividend_history(self.db, "TSMC")
        self.assertEqual(len(result), 1)

    def test_defaults_zero_when_missing_dividend_fields(self):
        rows = [{"date": "2025-06-15"}]  # no dividend values
        count = store_dividend_rows(self.db, "2330", rows)
        self.assertEqual(count, 1)
        result = get_dividend_history(self.db, "2330")
        self.assertEqual(result[0]["cash_dividend"], 0)
        self.assertEqual(result[0]["stock_dividend"], 0)


# ── TDCC Distribution ────────────────────────────────────────────────────────


class TestTdccDistribution(unittest.TestCase):
    def setUp(self):
        self.db = _db()

    def test_store_and_retrieve(self):
        rows = [
            {
                "date": "2025-01-10",
                "HoldingSharesLevel": "1-999",
                "people": 50000,
                "unit": 30000000,
                "percent": 1.5,
            },
            {
                "date": "2025-01-10",
                "HoldingSharesLevel": "1000+",
                "people": 1000,
                "unit": 200000000,
                "percent": 98.5,
            },
        ]
        count = store_tdcc_rows(self.db, "2330", rows)
        self.assertEqual(count, 2)

        result = get_tdcc_distribution(self.db, "2330")
        self.assertEqual(len(result), 2)
        levels = {r["level"] for r in result}
        self.assertEqual(levels, {"1-999", "1000+"})

    def test_skip_missing_date(self):
        rows = [{"date": "", "HoldingSharesLevel": "1-999", "people": 100}]
        count = store_tdcc_rows(self.db, "2330", rows)
        self.assertEqual(count, 0)

    def test_skip_missing_level(self):
        rows = [{"date": "2025-01-10", "HoldingSharesLevel": "", "people": 100}]
        count = store_tdcc_rows(self.db, "2330", rows)
        self.assertEqual(count, 0)

    def test_upsert_replaces(self):
        row = [{"date": "2025-01-10", "HoldingSharesLevel": "1-999", "people": 100, "unit": 500, "percent": 1.0}]
        store_tdcc_rows(self.db, "2330", row)
        row2 = [{"date": "2025-01-10", "HoldingSharesLevel": "1-999", "people": 200, "unit": 600, "percent": 2.0}]
        store_tdcc_rows(self.db, "2330", row2)
        result = get_tdcc_distribution(self.db, "2330")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["people"], 200)

    def test_limit_returns_latest_dates(self):
        for week in range(3):
            date = f"2025-01-{(week+1)*7:02d}"
            store_tdcc_rows(self.db, "2330", [
                {"date": date, "HoldingSharesLevel": "1-999", "people": 100, "unit": 500, "percent": 1.0},
            ])
        # Default limit=1 should return only the latest date
        result = get_tdcc_distribution(self.db, "2330", limit=1)
        self.assertTrue(all(r["date"] == "2025-01-21" for r in result))

        result2 = get_tdcc_distribution(self.db, "2330", limit=2)
        dates = {r["date"] for r in result2}
        self.assertEqual(len(dates), 2)

    def test_empty_result(self):
        self.assertEqual(get_tdcc_distribution(self.db, "NONE"), [])

    def test_symbol_normalised(self):
        store_tdcc_rows(self.db, " tsmc ", [
            {"date": "2025-01-10", "HoldingSharesLevel": "1-999", "people": 1, "unit": 1, "percent": 0.1},
        ])
        result = get_tdcc_distribution(self.db, "TSMC")
        self.assertEqual(len(result), 1)

    def test_alternate_keys_shares_and_pct(self):
        rows = [
            {
                "date": "2025-01-10",
                "HoldingSharesLevel": "1-999",
                "people": 50,
                "shares": 12345,
                "pct": 0.8,
            },
        ]
        count = store_tdcc_rows(self.db, "2330", rows)
        self.assertEqual(count, 1)
        result = get_tdcc_distribution(self.db, "2330")
        self.assertEqual(result[0]["shares"], 12345)
        self.assertAlmostEqual(result[0]["pct"], 0.8)

    def test_defaults_zero_when_missing_numeric_fields(self):
        rows = [{"date": "2025-01-10", "HoldingSharesLevel": "1-999"}]
        count = store_tdcc_rows(self.db, "2330", rows)
        self.assertEqual(count, 1)
        result = get_tdcc_distribution(self.db, "2330")
        self.assertEqual(result[0]["people"], 0)
        self.assertEqual(result[0]["shares"], 0)
        self.assertEqual(result[0]["pct"], 0)


if __name__ == "__main__":
    unittest.main()
