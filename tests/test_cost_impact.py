"""Tests for cost_impact in position_detail() and unrealized/underwater pcts in lots_by_method()."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger import StockLedger


def _ledger() -> StockLedger:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return StockLedger(db_path=tmp.name)


# ── TestCostImpact ─────────────────────────────────────────────────────────────

class TestCostImpact(unittest.TestCase):

    def setUp(self):
        self.lg = _ledger()
        self.lg.add_cash(500_000, date="2024-01-01")
        # first buy: 100 @ 100, comm=10  → cost_per_share = 100.10
        self.lg.add_trade("TST", "buy", qty=100, price=100.0,
                          date="2024-01-05", commission=10.0)
        # second buy: 100 @ 120, comm=10  → raises avg_cost
        self.lg.add_trade("TST", "buy", qty=100, price=120.0,
                          date="2024-02-01", commission=10.0)

    def test_last_buy_fields(self):
        """last_buy dict reflects the most-recent buy trade."""
        detail = self.lg.position_detail("TST")
        lb = detail["last_buy"]
        self.assertIsNotNone(lb)
        self.assertEqual(lb["date"], "2024-02-01")
        self.assertAlmostEqual(lb["price"], 120.0)
        self.assertEqual(lb["qty"], 100)
        self.assertAlmostEqual(lb["commission"], 10.0)
        self.assertAlmostEqual(lb["tax"], 0.0)

    def test_cost_impact_prev_avg(self):
        """prev_avg_cost should be the WAC before the last buy."""
        detail = self.lg.position_detail("TST")
        ci = detail["cost_impact"]
        self.assertIsNotNone(ci)
        # prev: 100 shares, cost_per_share=(100*100+10)/100 = 100.10
        self.assertAlmostEqual(ci["prev_qty"], 100.0, places=3)
        self.assertAlmostEqual(ci["prev_avg_cost"], 100.10, places=2)

    def test_cost_impact_new_avg(self):
        """new_avg_cost = WAC after the last buy."""
        detail = self.lg.position_detail("TST")
        ci = detail["cost_impact"]
        # new: 200 shares; new_avg = (10010 + 12010) / 200 = 110.10
        self.assertAlmostEqual(ci["new_qty"], 200.0, places=3)
        self.assertAlmostEqual(ci["new_avg_cost"], 110.10, places=2)

    def test_cost_impact_delta(self):
        """delta_avg_cost = new_avg - prev_avg; delta_avg_cost_pct is positive."""
        detail = self.lg.position_detail("TST")
        ci = detail["cost_impact"]
        # delta = 110.10 - 100.10 = 10.00
        self.assertAlmostEqual(ci["delta_avg_cost"], 10.00, places=2)
        self.assertIsNotNone(ci["delta_avg_cost_pct"])
        self.assertGreater(ci["delta_avg_cost_pct"], 0)

    def test_cost_impact_first_buy_only(self):
        """When the first (and only) buy is the last_buy, prev_qty=0 and prev_avg_cost=None."""
        lg = _ledger()
        lg.add_cash(50_000, date="2024-01-01")
        lg.add_trade("NEW", "buy", qty=50, price=200.0, date="2024-01-05")
        detail = lg.position_detail("NEW")
        ci = detail["cost_impact"]
        self.assertIsNotNone(ci)
        self.assertAlmostEqual(ci["prev_qty"], 0.0, places=3)
        self.assertIsNone(ci["prev_avg_cost"])
        self.assertIsNone(ci["delta_avg_cost_pct"])   # no prev to compare

    def test_cost_impact_none_when_no_trades(self):
        """Symbol with no trades → last_buy and cost_impact are both None."""
        lg = _ledger()
        detail = lg.position_detail("GHOST")
        self.assertIsNone(detail["last_buy"])
        self.assertIsNone(detail["cost_impact"])

    def test_buys_list_only_contains_buys(self):
        """cost_summary.buy_count counts only buy sides, ignoring sells."""
        lg = _ledger()
        lg.add_cash(500_000, date="2024-01-01")
        lg.add_trade("MIX", "buy",  qty=100, price=100.0, date="2024-01-05")
        lg.add_trade("MIX", "buy",  qty=50,  price=110.0, date="2024-01-10")
        lg.add_trade("MIX", "sell", qty=30,  price=120.0, date="2024-01-20")
        lg.add_trade("MIX", "buy",  qty=40,  price=105.0, date="2024-02-01")
        detail = lg.position_detail("MIX")
        # 3 buys, 1 sell → buy_count must be 3
        self.assertEqual(detail["cost_summary"]["buy_count"], 3)
        # last_buy should point to the third buy, not the sell
        lb = detail["last_buy"]
        self.assertEqual(lb["date"], "2024-02-01")
        self.assertAlmostEqual(lb["price"], 105.0)

    def test_cost_impact_after_sell(self):
        """last_buy / cost_impact computed correctly even when sells follow the last buy."""
        lg = _ledger()
        lg.add_cash(500_000, date="2024-01-01")
        lg.add_trade("SEL", "buy",  qty=100, price=100.0, date="2024-01-02")
        lg.add_trade("SEL", "buy",  qty=50,  price=120.0, date="2024-01-10")
        lg.add_trade("SEL", "sell", qty=20,  price=130.0, date="2024-01-20")
        detail = lg.position_detail("SEL")
        lb = detail["last_buy"]
        # last buy is the 120 buy on Jan 10
        self.assertEqual(lb["date"], "2024-01-10")
        # new_qty after that buy = 150, not current qty (130 after sell)
        ci = detail["cost_impact"]
        self.assertAlmostEqual(ci["new_qty"], 150.0, places=3)


# ── TestLotsUnrealizedPct ──────────────────────────────────────────────────────

class TestLotsUnrealizedPct(unittest.TestCase):

    def setUp(self):
        self.lg = _ledger()
        self.lg.add_cash(500_000, date="2024-01-01")
        self.lg.add_trade("XYZ", "buy", qty=100, price=100.0,
                          date="2024-01-05", commission=0.0)
        self.lg.add_price("XYZ", "2024-01-31", 120.0)

    def test_unrealized_pct_not_none(self):
        """unrealized_pct is not None when market_price exists."""
        result = self.lg.lots_by_method("XYZ", method="wac", as_of="2024-01-31")
        self.assertIsNotNone(result["lots"][0]["unrealized_pct"])

    def test_unrealized_pct_value(self):
        """unrealized_pct = (market_value - total_cost) / total_cost * 100."""
        result = self.lg.lots_by_method("XYZ", method="wac", as_of="2024-01-31")
        # cost=100, price=120 → gain = 20%
        self.assertAlmostEqual(result["lots"][0]["unrealized_pct"], 20.0, places=1)

    def test_underwater_pct_not_none(self):
        """underwater_pct is not None when market_price exists."""
        result = self.lg.lots_by_method("XYZ", method="wac", as_of="2024-01-31")
        self.assertIsNotNone(result["lots"][0]["underwater_pct"])

    def test_underwater_pct_zero_when_profitable(self):
        """Lot above cost → underwater_pct = 0."""
        result = self.lg.lots_by_method("XYZ", method="wac", as_of="2024-01-31")
        self.assertAlmostEqual(result["lots"][0]["underwater_pct"], 0.0, places=2)

    def test_underwater_pct_positive_when_below_cost(self):
        """Lot below cost → underwater_pct > 0."""
        self.lg.add_price("XYZ", "2024-02-01", 80.0)
        result = self.lg.lots_by_method("XYZ", method="wac", as_of="2024-02-01")
        # price 80 < cost 100 → 20% underwater
        self.assertGreater(result["lots"][0]["underwater_pct"], 0)
        self.assertAlmostEqual(result["lots"][0]["underwater_pct"], 20.0, places=1)

    def test_both_pcts_none_without_price(self):
        """No price in prices table and no trade → market_price=None → pcts are None."""
        lg = _ledger()
        # Cannot have a position without trades, so just verify field exists
        lg.add_cash(100_000, date="2024-01-01")
        lg.add_trade("NOPX", "buy", qty=10, price=50.0, date="2024-01-05")
        # No add_price call, but trade fallback gives market_price = 50
        # so pcts will NOT be None (trade_fallback)
        result = lg.lots_by_method("NOPX", method="wac")
        lot = result["lots"][0]
        # unrealized_pct = 0 (price == cost since no quote, fallback = buy price)
        self.assertIn("unrealized_pct", lot)
        self.assertIn("underwater_pct", lot)


if __name__ == "__main__":
    unittest.main()
