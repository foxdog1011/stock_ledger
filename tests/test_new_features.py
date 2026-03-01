"""Quick smoke test for cash void and trade tax features."""
import tempfile
import unittest
from pathlib import Path
from ledger import StockLedger


class TestCashVoid(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.l = StockLedger(Path(self._tmp) / "test.db")
        self.l.add_cash(10000, "2024-01-01", "initial")
        self.l.add_cash(500, "2024-01-02", "bonus")

    def test_balance_before_void(self):
        self.assertAlmostEqual(self.l.cash_balance("2024-01-02"), 10500)

    def test_void_cash_removes_from_balance(self):
        flow = self.l.cash_flow()
        bonus_id = next(e["id"] for e in flow if e["note"] == "bonus")
        self.l.void_cash(bonus_id)
        self.assertAlmostEqual(self.l.cash_balance("2024-01-02"), 10000)

    def test_void_hidden_by_default(self):
        flow = self.l.cash_flow()
        bonus_id = next(e["id"] for e in flow if e["note"] == "bonus")
        self.l.void_cash(bonus_id)
        flow_default = self.l.cash_flow()
        self.assertEqual(len(flow_default), 1)

    def test_include_void_shows_voided(self):
        flow = self.l.cash_flow()
        bonus_id = next(e["id"] for e in flow if e["note"] == "bonus")
        self.l.void_cash(bonus_id)
        flow_all = self.l.cash_flow(include_void=True)
        self.assertEqual(len(flow_all), 2)
        voided = next(e for e in flow_all if e["id"] == bonus_id)
        self.assertTrue(voided["is_void"])

    def test_void_balance_not_affected_by_voided(self):
        """Running balance in cash_flow should skip voided entries."""
        flow = self.l.cash_flow()
        bonus_id = next(e["id"] for e in flow if e["note"] == "bonus")
        self.l.void_cash(bonus_id)
        flow_all = self.l.cash_flow(include_void=True)
        # Both entries should show final balance of 10000
        for e in flow_all:
            if e["note"] == "initial":
                self.assertAlmostEqual(e["balance"], 10000)
            elif e["note"] == "bonus":
                # voided: balance doesn't change
                self.assertAlmostEqual(e["balance"], 10000)

    def test_duplicate_void_raises(self):
        flow = self.l.cash_flow()
        bonus_id = next(e["id"] for e in flow if e["note"] == "bonus")
        self.l.void_cash(bonus_id)
        with self.assertRaises(ValueError):
            self.l.void_cash(bonus_id)

    def test_void_not_found_raises(self):
        with self.assertRaises(ValueError):
            self.l.void_cash(9999)

    def test_cash_flow_id_field(self):
        flow = self.l.cash_flow()
        for e in flow:
            self.assertIn("id", e)
            self.assertIn("is_void", e)
            self.assertIsNotNone(e["id"])
            self.assertFalse(e["is_void"])


class TestTradeTax(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.l = StockLedger(Path(self._tmp) / "test.db")
        self.l.add_cash(20000, "2024-01-01")

    def test_buy_with_tax_reduces_cash(self):
        self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", commission=5, tax=3)
        # 20000 - (10*150 + 5 + 3) = 20000 - 1508 = 18492
        self.assertAlmostEqual(self.l.cash_balance("2024-01-02"), 18492)

    def test_buy_with_tax_avg_cost(self):
        self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", commission=5, tax=3)
        pnl = self.l.position_pnl("AAPL", "2024-01-02")
        # (1500 + 5 + 3) / 10 = 150.8
        self.assertAlmostEqual(pnl["avg_cost"], 150.8)

    def test_sell_with_tax_realized_pnl(self):
        self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", commission=5, tax=3)
        self.l.add_trade("AAPL", "sell", 10, 160, "2024-01-03", commission=5, tax=4)
        pnl = self.l.position_pnl("AAPL", "2024-01-03")
        # realized = (160 - 150.8)*10 - 5 - 4 = 92 - 9 = 83
        self.assertAlmostEqual(pnl["realized_pnl"], 83.0)

    def test_sell_with_tax_cash_impact(self):
        self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", commission=5, tax=3)
        self.l.add_trade("AAPL", "sell", 10, 160, "2024-01-03", commission=5, tax=4)
        # 18492 + (1600 - 5 - 4) = 18492 + 1591 = 20083
        self.assertAlmostEqual(self.l.cash_balance("2024-01-03"), 20083)

    def test_insufficient_cash_includes_tax(self):
        # cash=20000, try to buy 10*150 + 0 + 20001 = needs 21501 > 20000
        with self.assertRaises(ValueError):
            self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", commission=0, tax=20001)

    def test_negative_tax_raises(self):
        with self.assertRaises(ValueError):
            self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", tax=-1)

    def test_cash_flow_includes_tax_in_amount(self):
        self.l.add_trade("AAPL", "buy", 10, 150, "2024-01-02", commission=5, tax=3)
        flow = self.l.cash_flow()
        buy_entry = next(e for e in flow if e["type"] == "buy")
        # amount should be -(1500 + 5 + 3) = -1508
        self.assertAlmostEqual(buy_entry["amount"], -1508)


if __name__ == "__main__":
    unittest.main(verbosity=2)
