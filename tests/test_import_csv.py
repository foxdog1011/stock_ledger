"""Tests for CSV import parsing and validation logic.

Covers:
- _parse_csv: UTF-8 BOM handling, empty row skipping, column detection
- Import validation: required columns, field value constraints
- skipped count semantics: every row must resolve to either inserted or error;
  skipped is always 0 with the current implementation.

Note: These tests exercise the parsing and validation logic directly without
going through the FastAPI HTTP layer.  Router-level integration tests
(status codes, response shape) would require a TestClient setup and are
tracked as a future improvement.
"""
from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger import StockLedger


# ── Replicated from apps/api/routers/export_import._parse_csv ─────────────────
# Kept here so these tests have zero dependency on the FastAPI application
# context.  If the original function changes, update this copy accordingly.

def _parse_csv(content: bytes) -> list[dict]:
    """Decode (handles UTF-8 BOM) and parse CSV, skipping empty rows."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader if any(v.strip() for v in row.values())]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_ledger() -> StockLedger:
    tmp = tempfile.mkdtemp()
    return StockLedger(db_path=Path(tmp) / "test.db")


def _simulate_trades_import(csv_content: bytes, ledger: StockLedger, dry_run: bool = False) -> dict:
    """
    Simulate the import_trades validation loop from export_import.py.

    Mirrors the fixed logic: every row resolves to inserted or errors;
    skipped is always 0.
    """
    rows = _parse_csv(csv_content)
    required = {"date", "symbol", "side", "qty", "price"}
    inserted = 0
    skipped = 0  # always 0; no skip logic in current implementation
    errors: list[dict] = []

    for i, row in enumerate(rows, start=2):
        missing = required - set(k.strip() for k in row.keys())
        if missing:
            errors.append({"row": i, "message": f"Missing columns: {', '.join(sorted(missing))}", "raw": str(row)})
            continue
        try:
            date = row["date"].strip()
            symbol = row["symbol"].strip().upper()
            side = row["side"].strip().lower()
            qty = float(row["qty"])
            price = float(row["price"])
            commission = float(row.get("commission", "") or 0)
            tax = float(row.get("tax", "") or 0)
            note = row.get("note", "").strip()
            if not date or not symbol:
                raise ValueError("date and symbol are required")
            if side not in ("buy", "sell"):
                raise ValueError(f"side must be 'buy' or 'sell', got '{side}'")
            if qty <= 0:
                raise ValueError("qty must be > 0")
            if price <= 0:
                raise ValueError("price must be > 0")
            if commission < 0 or tax < 0:
                raise ValueError("commission and tax must be >= 0")
        except ValueError as exc:
            errors.append({"row": i, "message": str(exc), "raw": str(row)})
            continue

        if dry_run:
            inserted += 1
        else:
            try:
                ledger.add_trade(symbol=symbol, side=side, qty=qty, price=price,
                                 date=date, commission=commission, tax=tax, note=note)
                inserted += 1
            except Exception as exc:
                errors.append({"row": i, "message": str(exc), "raw": str(row)})

    return {"ok": len(errors) == 0, "inserted": inserted, "skipped": skipped, "errors": errors, "dry_run": dry_run}


# ── _parse_csv unit tests ──────────────────────────────────────────────────────

class TestParseCsv(unittest.TestCase):

    def test_basic_parse_returns_rows(self):
        content = b"date,symbol,side,qty,price\n2024-01-01,AAPL,buy,10,150.0\n"
        rows = _parse_csv(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "AAPL")
        self.assertEqual(rows[0]["side"], "buy")

    def test_utf8_bom_is_stripped(self):
        # Files saved from Excel often have a UTF-8 BOM prefix.
        # Encode with "utf-8-sig" (NOT pre-inserting \ufeff manually)
        # to produce a correctly formed BOM-prefixed byte sequence.
        content = "date,symbol,side,qty,price\n2024-01-01,TSLA,buy,5,200.0\n".encode("utf-8-sig")
        rows = _parse_csv(content)
        self.assertEqual(len(rows), 1)
        # BOM must not appear in the column name after decoding
        self.assertIn("date", rows[0])
        self.assertNotIn("\ufeffdate", rows[0])

    def test_empty_rows_are_skipped(self):
        content = b"date,symbol,side,qty,price\n\n2024-01-01,AAPL,buy,10,150.0\n\n"
        rows = _parse_csv(content)
        self.assertEqual(len(rows), 1)

    def test_multiple_valid_rows(self):
        content = (
            b"date,symbol,side,qty,price\n"
            b"2024-01-01,AAPL,buy,10,150.0\n"
            b"2024-01-02,TSLA,buy,5,200.0\n"
        )
        rows = _parse_csv(content)
        self.assertEqual(len(rows), 2)

    def test_missing_required_column_is_detectable(self):
        """Column detection: verify that a CSV without 'side' is identifiable."""
        required = {"date", "symbol", "side", "qty", "price"}
        content = b"date,symbol,qty,price\n2024-01-01,AAPL,10,150.0\n"
        rows = _parse_csv(content)
        headers = set(k.strip() for k in rows[0].keys())
        missing = required - headers
        self.assertIn("side", missing)
        self.assertEqual(len(missing), 1)

    def test_all_required_columns_present(self):
        required = {"date", "symbol", "side", "qty", "price"}
        content = b"date,symbol,side,qty,price\n2024-01-01,AAPL,buy,10,150.0\n"
        rows = _parse_csv(content)
        headers = set(k.strip() for k in rows[0].keys())
        self.assertEqual(required - headers, set())


# ── Import validation + skipped count tests ────────────────────────────────────

class TestImportValidation(unittest.TestCase):

    def setUp(self):
        self.ledger = _make_ledger()
        self.ledger.add_cash(1_000_000, "2023-01-01")

    def test_valid_csv_all_inserted_skipped_zero(self):
        """All valid rows → inserted = N, skipped = 0, errors = []."""
        content = (
            b"date,symbol,side,qty,price\n"
            b"2024-01-02,AAPL,buy,10,150.0\n"
            b"2024-01-03,TSLA,buy,5,200.0\n"
        )
        result = _simulate_trades_import(content, self.ledger)
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["errors"], [])

    def test_invalid_side_goes_to_errors_not_skipped(self):
        """A row with an invalid 'side' must appear in errors, not skipped."""
        content = b"date,symbol,side,qty,price\n2024-01-02,AAPL,hold,10,150.0\n"
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("side", result["errors"][0]["message"])

    def test_mixed_valid_and_invalid_rows(self):
        """2 valid + 1 invalid → inserted=2, skipped=0, errors=1."""
        content = (
            b"date,symbol,side,qty,price\n"
            b"2024-01-02,AAPL,buy,10,150.0\n"
            b"2024-01-03,TSLA,hold,5,200.0\n"   # invalid side
            b"2024-01-04,MSFT,buy,8,300.0\n"
        )
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["errors"]), 1)

    def test_missing_required_column_is_an_error(self):
        """CSV without 'side' column: all rows flagged as errors."""
        content = b"date,symbol,qty,price\n2024-01-02,AAPL,10,150.0\n"
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("side", result["errors"][0]["message"])

    def test_inserted_plus_errors_equals_total_rows(self):
        """Invariant: inserted + len(errors) == total data rows (skipped always 0)."""
        content = (
            b"date,symbol,side,qty,price\n"
            b"2024-01-02,AAPL,buy,10,150.0\n"
            b"2024-01-03,TSLA,INVALID,5,200.0\n"
            b"2024-01-04,MSFT,buy,8,300.0\n"
            b"bad-date,,sell,-1,-1\n"             # multiple validation failures
        )
        result = _simulate_trades_import(content, self.ledger)
        total = result["inserted"] + result["skipped"] + len(result["errors"])
        # 4 data rows
        self.assertEqual(total, 4)
        self.assertEqual(result["skipped"], 0)

    def test_dry_run_does_not_write_to_ledger(self):
        """dry_run=True: inserted count reflects validated rows but nothing is written."""
        content = b"date,symbol,side,qty,price\n2024-01-02,AAPL,buy,10,150.0\n"
        result = _simulate_trades_import(content, self.ledger, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertTrue(result["dry_run"])
        # Position must be 0 — nothing written
        self.assertEqual(self.ledger.position("AAPL"), 0)

    def test_negative_qty_is_an_error(self):
        content = b"date,symbol,side,qty,price\n2024-01-02,AAPL,buy,-5,150.0\n"
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["errors"]), 1)

    def test_negative_price_is_an_error(self):
        content = b"date,symbol,side,qty,price\n2024-01-02,AAPL,buy,10,-150.0\n"
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["errors"]), 1)

    def test_negative_commission_is_an_error(self):
        content = b"date,symbol,side,qty,price,commission\n2024-01-02,AAPL,buy,10,150.0,-1\n"
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["skipped"], 0)

    def test_negative_tax_is_an_error(self):
        content = b"date,symbol,side,qty,price,commission,tax\n2024-01-02,AAPL,buy,10,150.0,0,-5\n"
        result = _simulate_trades_import(content, self.ledger)
        self.assertFalse(result["ok"])
        self.assertEqual(result["skipped"], 0)

    def test_row_error_number_reflects_csv_line(self):
        """Error row numbers should be 1-indexed with header as row 1."""
        content = (
            b"date,symbol,side,qty,price\n"
            b"2024-01-02,AAPL,buy,10,150.0\n"   # row 2 — valid
            b"2024-01-03,TSLA,hold,5,200.0\n"   # row 3 — invalid
        )
        result = _simulate_trades_import(content, self.ledger)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["row"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
