"""Tests for domain.execution.offsetting."""
import tempfile
import unittest

from ledger import StockLedger
from domain.execution.offsetting import (
    losing_positions,
    profit_inventory,
    simulate_offsetting,
)


def _ledger() -> StockLedger:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    lg = StockLedger(db_path=tmp.name)
    lg.add_cash(500_000, "2024-01-01")
    return lg


# ── losing_positions ──────────────────────────────────────────────────────────

class TestLosingPositions(unittest.TestCase):
    def test_empty_when_all_profitable(self):
        lg = _ledger()
        lg.add_trade("AAPL", "buy", 100, 180.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-15", 200.0)
        self.assertEqual(losing_positions(lg), [])

    def test_lists_underwater_position(self):
        lg = _ledger()
        lg.add_trade("AAPL", "buy", 100, 200.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-15", 150.0)
        result = losing_positions(lg)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["symbol"], "AAPL")
        self.assertLess(result[0]["unrealized_pnl"], 0)

    def test_excludes_position_with_no_price(self):
        # trade fallback: buy @ 200, last_price = 200 → unrealized = 0 → excluded
        lg = _ledger()
        lg.add_trade("AAPL", "buy", 100, 200.0, "2024-01-10")
        result = losing_positions(lg)
        self.assertEqual(result, [])

    def test_sorted_largest_loss_first(self):
        lg = _ledger()
        lg.add_trade("AAPL", "buy", 100, 200.0, "2024-01-10")
        lg.add_trade("MSFT", "buy",  50, 300.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-15", 100.0)   # loss = -10000
        lg.add_price("MSFT", "2024-01-15", 250.0)   # loss = -2500
        result = losing_positions(lg)
        self.assertEqual(result[0]["symbol"], "AAPL")

    def test_loss_if_full_exit_is_abs_unrealized(self):
        lg = _ledger()
        lg.add_trade("AAPL", "buy", 100, 200.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-15", 150.0)
        r = losing_positions(lg)[0]
        self.assertAlmostEqual(r["loss_if_full_exit"], abs(r["unrealized_pnl"]))


# ── profit_inventory ──────────────────────────────────────────────────────────

class TestProfitInventory(unittest.TestCase):
    def setUp(self):
        self.lg = _ledger()
        # AAPL: buy 100@180, sell 100@220 → realized = +4000
        self.lg.add_trade("AAPL", "buy",  100, 180.0, "2024-01-10")
        self.lg.add_trade("AAPL", "sell", 100, 220.0, "2024-02-01")
        # MSFT: buy 50@300, sell 50@280 → realized = -1000
        self.lg.add_trade("MSFT", "buy",  50, 300.0, "2024-01-10")
        self.lg.add_trade("MSFT", "sell", 50, 280.0, "2024-02-01")

    def test_summary_keys(self):
        pi = profit_inventory(self.lg)
        self.assertIn("summary", pi)
        self.assertIn("by_symbol", pi)
        for k in ("gross_realized_pnl", "positive_realized_pnl", "available_to_offset"):
            self.assertIn(k, pi["summary"])

    def test_gross_realized_pnl(self):
        pi = profit_inventory(self.lg)
        self.assertAlmostEqual(pi["summary"]["gross_realized_pnl"], 3000.0)

    def test_positive_realized_pnl(self):
        pi = profit_inventory(self.lg)
        self.assertAlmostEqual(pi["summary"]["positive_realized_pnl"], 4000.0)

    def test_available_to_offset(self):
        pi = profit_inventory(self.lg)
        self.assertAlmostEqual(pi["summary"]["available_to_offset"], 3000.0)

    def test_available_to_offset_zero_when_net_negative(self):
        lg = _ledger()
        lg.add_trade("AAPL", "buy",  100, 200.0, "2024-01-10")
        lg.add_trade("AAPL", "sell", 100, 150.0, "2024-02-01")
        pi = profit_inventory(lg)
        self.assertEqual(pi["summary"]["available_to_offset"], 0.0)

    def test_by_symbol_sorted_desc(self):
        pi = profit_inventory(self.lg)
        pnls = [r["realized_pnl"] for r in pi["by_symbol"]]
        self.assertEqual(pnls, sorted(pnls, reverse=True))

    def test_by_symbol_entry_keys(self):
        pi = profit_inventory(self.lg)
        for entry in pi["by_symbol"]:
            for k in ("symbol", "realized_pnl", "qty"):
                self.assertIn(k, entry)


# ── simulate_offsetting ───────────────────────────────────────────────────────

class TestSimulateOffsetting(unittest.TestCase):
    def setUp(self):
        self.lg = _ledger()
        # TSLA: buy 100@300 → will be the losing position
        self.lg.add_trade("TSLA", "buy", 100, 300.0, "2024-01-10")
        self.lg.add_price("TSLA", "2024-02-01", 250.0)  # unrealized = -5000
        # AAPL: buy+sell → realized gain = +4000
        self.lg.add_trade("AAPL", "buy",  100, 180.0, "2024-01-10")
        self.lg.add_trade("AAPL", "sell", 100, 220.0, "2024-02-01")

    def test_output_keys(self):
        r = simulate_offsetting(self.lg, "TSLA")
        for k in ("as_of", "losing_position", "profit_inventory", "simulation", "guardrail"):
            self.assertIn(k, r)

    def test_losing_position_populated_for_underwater(self):
        r = simulate_offsetting(self.lg, "TSLA")
        self.assertIsNotNone(r["losing_position"])
        self.assertLess(r["losing_position"]["unrealized_pnl"], 0)

    def test_losing_position_none_for_profitable(self):
        # AAPL already fully closed; query an open profitable position
        lg = _ledger()
        lg.add_trade("AAPL", "buy", 100, 180.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-15", 200.0)
        r = simulate_offsetting(lg, "AAPL")
        self.assertIsNone(r["losing_position"])

    def test_sim_qty_defaults_to_full_position(self):
        r = simulate_offsetting(self.lg, "TSLA")
        self.assertEqual(r["simulation"]["sim_qty"], 100.0)

    def test_sim_price_defaults_to_last_price(self):
        r = simulate_offsetting(self.lg, "TSLA")
        self.assertEqual(r["simulation"]["sim_price"], 250.0)

    def test_sim_realized_loss_negative(self):
        r = simulate_offsetting(self.lg, "TSLA")
        self.assertLess(r["simulation"]["sim_realized_loss"], 0)

    def test_warnings_always_empty(self):
        r = simulate_offsetting(self.lg, "TSLA")
        self.assertEqual(r["guardrail"]["warnings"], [])

    # ── guardrail: pass ──────────────────────────────────────────────────

    def test_guardrail_pass_normal(self):
        # loss=-5000, available=4000 → over_offset? projected = 4000-5000 = -1000 → fail
        # use partial qty so projected >= 0: sell 50 @ 250 → loss=-2500, projected=4000-2500=1500
        r = simulate_offsetting(self.lg, "TSLA", qty=50, price=250.0)
        self.assertTrue(r["guardrail"]["passed"])
        self.assertIsNone(r["guardrail"]["reason"])

    # ── guardrail: fail cases ────────────────────────────────────────────

    def test_guardrail_no_price(self):
        lg = _ledger()
        lg.add_trade("TSLA", "buy", 100, 300.0, "2024-01-10")
        # no price added → last_price = trade fallback (300) → not a loss
        # force no price by passing price=None and clearing prices
        r = simulate_offsetting(lg, "TSLA", price=None)
        # trade fallback = 300 = avg_cost → sim_realized_loss = 0 → not_a_loss
        self.assertFalse(r["guardrail"]["passed"])

    def test_guardrail_no_price_explicit(self):
        # Symbol with no trades and no price → qty=0, sim_price=None
        r = simulate_offsetting(self.lg, "ZZZZ", qty=1, price=None)
        self.assertFalse(r["guardrail"]["passed"])
        self.assertEqual(r["guardrail"]["reason"], "no_price")

    def test_guardrail_qty_exceeds_position(self):
        r = simulate_offsetting(self.lg, "TSLA", qty=200, price=250.0)
        self.assertFalse(r["guardrail"]["passed"])
        self.assertEqual(r["guardrail"]["reason"], "qty_exceeds_position")

    def test_guardrail_not_a_loss(self):
        # sell above avg_cost → profit, not loss
        r = simulate_offsetting(self.lg, "TSLA", qty=50, price=350.0)
        self.assertFalse(r["guardrail"]["passed"])
        self.assertEqual(r["guardrail"]["reason"], "not_a_loss")

    def test_guardrail_over_offset(self):
        # sell all 100 @ 250 → loss=-5000; available=4000; projected=-1000 < 0
        r = simulate_offsetting(self.lg, "TSLA", qty=100, price=250.0)
        self.assertFalse(r["guardrail"]["passed"])
        self.assertEqual(r["guardrail"]["reason"], "over_offset")

    def test_projected_gross_realized_correct(self):
        r = simulate_offsetting(self.lg, "TSLA", qty=50, price=250.0)
        expected = round(
            r["profit_inventory"]["summary"]["gross_realized_pnl"]
            + r["simulation"]["sim_realized_loss"],
            2,
        )
        self.assertAlmostEqual(r["simulation"]["projected_gross_realized_pnl"], expected)

    def test_commission_not_included_flag(self):
        r = simulate_offsetting(self.lg, "TSLA")
        self.assertTrue(r["simulation"]["commission_not_included"])


if __name__ == "__main__":
    unittest.main()
