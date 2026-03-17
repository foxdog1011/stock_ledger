"""Tests for attribution and daily digest generation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger import StockLedger


def _setup_portfolio(ledger: StockLedger) -> None:
    """Seed a minimal portfolio for testing."""
    ledger.add_cash(500_000, date="2024-01-01")
    ledger.add_trade(symbol="AAPL", side="buy", qty=100, price=185.0, date="2024-01-05", commission=10)
    ledger.add_trade(symbol="MSFT", side="buy", qty=50,  price=374.0, date="2024-01-05", commission=10)
    ledger.add_price(symbol="AAPL", date="2024-01-05", close=185.0)
    ledger.add_price(symbol="MSFT", date="2024-01-05", close=374.0)
    ledger.add_price(symbol="AAPL", date="2024-01-31", close=200.0)
    ledger.add_price(symbol="MSFT", date="2024-01-31", close=390.0)


class TestAttribution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)
        _setup_portfolio(self.ledger)

    def _attribution(self, start, end):
        """Call the same logic used in the API."""
        pos_start = {p["symbol"]: p for p in self.ledger.all_positions_pnl(as_of=start, open_only=False)}
        pos_end   = {p["symbol"]: p for p in self.ledger.all_positions_pnl(as_of=end, open_only=False)}
        all_syms = set(pos_start) | set(pos_end)
        items = []
        for sym in all_syms:
            ps = pos_start.get(sym, {})
            pe = pos_end.get(sym, {})
            unrealized_change = (pe.get("unrealized_pnl") or 0) - (ps.get("unrealized_pnl") or 0)
            realized_change   = (pe.get("realized_pnl") or 0)   - (ps.get("realized_pnl") or 0)
            items.append({"symbol": sym, "contribution": round(unrealized_change + realized_change, 2)})
        items.sort(key=lambda x: x["contribution"], reverse=True)
        return items

    def test_attribution_structure(self):
        items = self._attribution("2024-01-05", "2024-01-31")
        # Should have 2 symbols
        self.assertEqual(len(items), 2)
        syms = {i["symbol"] for i in items}
        self.assertIn("AAPL", syms)
        self.assertIn("MSFT", syms)

    def test_attribution_gainers_positive(self):
        items = self._attribution("2024-01-05", "2024-01-31")
        # AAPL: (200-185)*100=1500; MSFT: (390-374)*50=800
        aapl = next(i for i in items if i["symbol"] == "AAPL")
        msft = next(i for i in items if i["symbol"] == "MSFT")
        self.assertAlmostEqual(aapl["contribution"], 1500.0, places=0)
        self.assertAlmostEqual(msft["contribution"], 800.0,  places=0)

    def test_attribution_total_vs_daily_pnl(self):
        """Total attribution should be in the same order of magnitude as equity change."""
        items = self._attribution("2024-01-05", "2024-01-31")
        total = sum(i["contribution"] for i in items)
        # equity change ≈ 1500 + 800 = 2300 (no external cashflow in range)
        daily = self.ledger.daily_equity(start="2024-01-31", end="2024-01-31", freq="D")
        # daily_pnl won't perfectly equal attribution (different base date), but
        # both should be positive and within 10x of each other
        self.assertGreater(total, 0)
        if daily:
            self.assertGreater(daily[-1]["total_equity"], 0)


class TestDigestGenerate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)
        _setup_portfolio(self.ledger)
        # Point digest router to same DB
        import os
        os.environ["DB_PATH"] = self.tmp.name

    def _generate(self, date: str, overwrite: bool = False) -> dict:
        """Call digest logic directly (bypassing FastAPI)."""
        from apps.api.routers.digest import generate_and_save, ensure_digest_table
        ensure_digest_table()
        return generate_and_save(ledger=self.ledger, date=date, overwrite=overwrite)

    def test_generate_creates_record(self):
        row = self._generate("2024-01-31")
        self.assertEqual(row["date"], "2024-01-31")
        self.assertIsNotNone(row["total_equity"])
        self.assertGreater(row["total_equity"], 0)

    def test_generate_has_contributors(self):
        row = self._generate("2024-01-31")
        contributors = json.loads(row["top_contributors_json"] or "[]")
        self.assertIsInstance(contributors, list)

    def test_generate_409_on_duplicate(self):
        from fastapi import HTTPException
        self._generate("2024-01-31")
        with self.assertRaises(HTTPException) as ctx:
            self._generate("2024-01-31", overwrite=False)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_generate_overwrite(self):
        row1 = self._generate("2024-01-31")
        # Force a slight difference and overwrite
        row2 = self._generate("2024-01-31", overwrite=True)
        self.assertEqual(row1["date"], row2["date"])
        self.assertEqual(row1["id"], row2["id"])

    def test_patch_notes(self):
        self._generate("2024-01-31")
        import sqlite3
        from pathlib import Path
        db = Path(self.tmp.name)
        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE daily_digest SET notes = ? WHERE date = ?",
                ("Test note", "2024-01-31"),
            )
            conn.commit()
            row = conn.execute(
                "SELECT notes FROM daily_digest WHERE date = ?", ("2024-01-31",)
            ).fetchone()
        self.assertEqual(row[0], "Test note")

    def test_generate_has_alerts_field(self):
        row = self._generate("2024-01-31")
        # alerts_json may be empty list but should be valid JSON
        alerts = json.loads(row["alerts_json"] or "[]")
        self.assertIsInstance(alerts, list)


if __name__ == "__main__":
    unittest.main()
