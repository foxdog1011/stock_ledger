"""Tests for daily_equity(), lots_by_method(), and position_detail()."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger import StockLedger


def _ledger() -> StockLedger:
    """File-based temp ledger (avoid :memory: per-connection isolation)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return StockLedger(db_path=tmp.name)


class TestDailyEquity(unittest.TestCase):

    def setUp(self):
        self.lg = _ledger()
        self.lg.add_cash(100_000, date="2024-01-02", note="deposit")
        self.lg.add_trade("AAPL", "buy", qty=10, price=150.0,
                          date="2024-01-03", commission=5.0)
        self.lg.add_price("AAPL", "2024-01-05", 160.0)

    def test_basic_shape(self):
        rows = self.lg.daily_equity("2024-01-02", "2024-01-05", freq="D")
        self.assertEqual(len(rows), 4)  # Jan 2, 3, 4, 5
        required_fields = {
            "date", "cash", "market_value", "total_equity",
            "external_cashflow", "daily_change", "daily_pnl",
            "daily_return_pct", "price_staleness_days", "used_quote_date_map",
        }
        for row in rows:
            self.assertTrue(required_fields.issubset(row.keys()),
                            f"Missing fields: {required_fields - set(row.keys())}")

    def test_daily_pnl_excludes_cashflow(self):
        # On Jan 2, 100K is deposited; daily_change = daily_pnl + external_cashflow
        rows = self.lg.daily_equity("2024-01-02", "2024-01-02", freq="D")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertAlmostEqual(r["external_cashflow"], 100_000, places=1)
        self.assertAlmostEqual(
            r["daily_change"], r["daily_pnl"] + r["external_cashflow"], places=2
        )

    def test_return_pct_null_when_prev_zero(self):
        # Very first day: previous equity is 0 → daily_return_pct must be None
        rows = self.lg.daily_equity("2024-01-02", "2024-01-05", freq="D")
        self.assertIsNone(rows[0]["daily_return_pct"])

    def test_business_freq_excludes_weekends(self):
        # 2024-01-06 is Saturday, 2024-01-07 is Sunday
        rows = self.lg.daily_equity("2024-01-05", "2024-01-09", freq="B")
        dates = [r["date"] for r in rows]
        self.assertNotIn("2024-01-06", dates)
        self.assertNotIn("2024-01-07", dates)
        self.assertIn("2024-01-08", dates)  # Monday


class TestLotsByMethod(unittest.TestCase):

    def setUp(self):
        self.lg = _ledger()
        self.lg.add_cash(500_000, date="2024-01-01")
        # lot 1: buy 100 @ 100
        self.lg.add_trade("TST", "buy", qty=100, price=100.0,
                          date="2024-01-02", commission=0.0)
        # lot 2: buy 100 @ 120
        self.lg.add_trade("TST", "buy", qty=100, price=120.0,
                          date="2024-01-03", commission=0.0)
        # sell 150 — FIFO consumes lot1(100) + lot2(50)
        self.lg.add_trade("TST", "sell", qty=150, price=130.0,
                          date="2024-01-10", commission=0.0)

    def test_fifo_lot_pairing(self):
        result = self.lg.lots_by_method("TST", method="fifo")
        self.assertEqual(result["position_qty"], 50.0)
        rb = result["realized_breakdown"]
        self.assertEqual(len(rb), 1)
        allocs = rb[0]["allocations"]
        self.assertEqual(allocs[0]["lot_id"], 1)
        self.assertEqual(allocs[0]["qty"], 100)
        self.assertEqual(allocs[1]["lot_id"], 2)
        self.assertEqual(allocs[1]["qty"], 50)

    def test_lifo_lot_pairing(self):
        result = self.lg.lots_by_method("TST", method="lifo")
        self.assertEqual(result["position_qty"], 50.0)
        rb = result["realized_breakdown"]
        self.assertEqual(len(rb), 1)
        allocs = rb[0]["allocations"]
        lot_ids = [a["lot_id"] for a in allocs]
        self.assertIn(2, lot_ids)
        self.assertIn(1, lot_ids)
        lot2 = next(a for a in allocs if a["lot_id"] == 2)
        lot1 = next(a for a in allocs if a["lot_id"] == 1)
        self.assertEqual(lot2["qty"], 100)
        self.assertEqual(lot1["qty"], 50)

    def test_wac_no_realized_breakdown(self):
        result = self.lg.lots_by_method("TST", method="wac")
        self.assertEqual(result["realized_breakdown"], [])
        self.assertGreater(len(result["lots"]), 0)

    def test_voided_trade_excluded(self):
        lg = _ledger()
        lg.add_cash(500_000, date="2024-01-01")
        lg.add_trade("VOD", "buy", qty=100, price=50.0, date="2024-01-02")
        lg.add_trade("VOD", "buy", qty=50, price=60.0, date="2024-01-03")
        # Get id of the second trade via trade_history
        history = lg.trade_history()
        t2_id = history[-1]["id"]
        lg.void_trade(t2_id)
        result = lg.lots_by_method("VOD", method="fifo")
        self.assertAlmostEqual(result["position_qty"], 100.0, places=3)
        self.assertEqual(len(result["lots"]), 1)


class TestPositionDetail(unittest.TestCase):

    def test_running_wac_shape(self):
        lg = _ledger()
        lg.add_cash(500_000, date="2024-01-01")
        lg.add_trade("XYZ", "buy", qty=100, price=10.0,
                     date="2024-01-02", commission=5.0)
        lg.add_trade("XYZ", "buy", qty=200, price=12.0,
                     date="2024-01-05", commission=5.0)

        detail = lg.position_detail("XYZ")
        rw = detail["running_wac"]
        self.assertEqual(len(rw), 2)

        # First buy: cost_per_share = (100*10 + 5) / 100 = 10.05
        self.assertAlmostEqual(rw[0]["avg_cost_after"], 10.05, places=4)

        # Second buy WAC: (1005 + 200*12+5) / 300 = 3410/300
        expected_wac = (1005 + 2405) / 300
        self.assertAlmostEqual(rw[1]["avg_cost_after"], expected_wac, places=4)

        # wac_series: 2 buy entries, both leave shares > 0
        self.assertEqual(len(detail["wac_series"]), 2)


if __name__ == "__main__":
    unittest.main()
