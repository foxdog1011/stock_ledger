"""Boundary-condition tests for domain.risk.adjusted."""
import tempfile
import unittest

from ledger import StockLedger
from domain.risk.adjusted import position_adjusted_risk, all_positions_adjusted_risk

_EXPECTED_KEYS = {
    # from position_pnl
    "symbol", "qty", "avg_cost", "realized_pnl", "unrealized_pnl",
    "last_price", "price_source", "market_value",
    # added by position_adjusted_risk
    "position_state", "cost_basis_remaining", "net_at_risk",
    "pct_recovered", "amount_to_recover", "total_pnl",
}

_OPEN_STATES  = ("risk_free", "at_risk")
_VALID_STATES = ("risk_free", "at_risk", "closed", "no_position")


def _ledger_with_cash(amount=200_000) -> StockLedger:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    lg = StockLedger(db_path=tmp.name)
    lg.add_cash(amount, "2024-01-01")
    return lg


class TestOutputContract(unittest.TestCase):
    def setUp(self):
        self.lg = _ledger_with_cash()
        self.lg.add_trade("AAPL", "buy", 100, 180.0, "2024-01-10", commission=5.0)
        self.lg.add_price("AAPL", "2024-01-15", 200.0)

    def test_all_keys_present(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertEqual(set(r.keys()), _EXPECTED_KEYS)

    def test_position_state_valid_value(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertIn(r["position_state"], _VALID_STATES)


# ── no_position ──────────────────────────────────────────────────────────────

class TestNoPosition(unittest.TestCase):
    def setUp(self):
        self.lg = _ledger_with_cash()

    def test_state(self):
        r = position_adjusted_risk(self.lg, "ZZZZ")
        self.assertEqual(r["position_state"], "no_position")

    def test_risk_fields_none(self):
        r = position_adjusted_risk(self.lg, "ZZZZ")
        for key in ("cost_basis_remaining", "net_at_risk",
                    "pct_recovered", "amount_to_recover", "total_pnl"):
            self.assertIsNone(r[key], f"{key} should be None for no_position")

    def test_qty_zero(self):
        r = position_adjusted_risk(self.lg, "ZZZZ")
        self.assertEqual(r["qty"], 0.0)


# ── closed ───────────────────────────────────────────────────────────────────

class TestClosed(unittest.TestCase):
    def _make_closed(self, buy_price, sell_price):
        lg = _ledger_with_cash()
        lg.add_trade("AAPL", "buy",  100, buy_price,  "2024-01-10")
        lg.add_trade("AAPL", "sell", 100, sell_price, "2024-02-01")
        return lg

    def test_state_after_full_sell(self):
        lg = self._make_closed(180.0, 200.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["position_state"], "closed")

    def test_total_pnl_equals_realized_when_gain(self):
        lg = self._make_closed(180.0, 200.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["total_pnl"], r["realized_pnl"])
        self.assertGreater(r["total_pnl"], 0)

    def test_total_pnl_equals_realized_when_loss(self):
        lg = self._make_closed(200.0, 150.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["total_pnl"], r["realized_pnl"])
        self.assertLess(r["total_pnl"], 0)

    def test_total_pnl_equals_realized_when_breakeven(self):
        lg = self._make_closed(180.0, 180.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["total_pnl"], r["realized_pnl"])

    def test_risk_fields_none_for_closed(self):
        lg = self._make_closed(180.0, 200.0)
        r  = position_adjusted_risk(lg, "AAPL")
        for key in ("cost_basis_remaining", "net_at_risk",
                    "pct_recovered", "amount_to_recover"):
            self.assertIsNone(r[key], f"{key} should be None for closed")


# ── at_risk ───────────────────────────────────────────────────────────────────

class TestAtRisk(unittest.TestCase):
    def setUp(self):
        self.lg = _ledger_with_cash()
        # buy 100 @ 180, no sells → realized=0, cost_basis=18000
        self.lg.add_trade("AAPL", "buy", 100, 180.0, "2024-01-10", commission=0.0)

    def test_state_first_buy_no_sell(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertEqual(r["position_state"], "at_risk")

    def test_cost_basis_remaining(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertAlmostEqual(r["cost_basis_remaining"], 18000.0)

    def test_net_at_risk_equals_cost_basis_when_no_realized(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertAlmostEqual(r["net_at_risk"], 18000.0)

    def test_pct_recovered_zero(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertAlmostEqual(r["pct_recovered"], 0.0)

    def test_amount_to_recover_equals_net_at_risk(self):
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertAlmostEqual(r["amount_to_recover"], r["net_at_risk"])

    def test_total_pnl_with_price(self):
        self.lg.add_price("AAPL", "2024-01-15", 190.0)
        r = position_adjusted_risk(self.lg, "AAPL")
        expected = round(r["realized_pnl"] + r["unrealized_pnl"], 2)
        self.assertEqual(r["total_pnl"], expected)

    def test_partial_sell_still_at_risk(self):
        # sell 10 @ 200 → realized = (200-180)*10 = 200; cost_basis_remaining = 90*180 = 16200
        self.lg.add_trade("AAPL", "sell", 10, 200.0, "2024-02-01")
        r = position_adjusted_risk(self.lg, "AAPL")
        self.assertEqual(r["position_state"], "at_risk")
        self.assertGreater(r["net_at_risk"], 0)
        self.assertGreater(r["pct_recovered"], 0)


# ── risk_free ─────────────────────────────────────────────────────────────────

class TestRiskFree(unittest.TestCase):
    def _make_risk_free(self, extra_realized=0.0):
        """Buy 100 @ 180, sell 50 @ price that recovers full cost basis of remaining 50."""
        # remaining cost = 50 * 180 = 9000
        # need realized >= 9000 from selling 50 shares
        # sell price p: (p - 180) * 50 >= 9000 → p >= 360
        lg = _ledger_with_cash()
        lg.add_trade("AAPL", "buy",  100, 180.0, "2024-01-10")
        sell_price = 360.0 + extra_realized / 50
        lg.add_trade("AAPL", "sell",  50, sell_price, "2024-02-01")
        return lg

    def test_state_exactly_recovered(self):
        lg = self._make_risk_free(extra_realized=0.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["position_state"], "risk_free")

    def test_net_at_risk_zero_when_exactly_recovered(self):
        lg = self._make_risk_free(extra_realized=0.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertAlmostEqual(r["net_at_risk"], 0.0, places=2)

    def test_amount_to_recover_zero(self):
        lg = self._make_risk_free(extra_realized=0.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["amount_to_recover"], 0.0)

    def test_pct_recovered_gte_100(self):
        lg = self._make_risk_free(extra_realized=0.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertGreaterEqual(r["pct_recovered"], 100.0)

    def test_state_over_recovered(self):
        lg = self._make_risk_free(extra_realized=1000.0)
        r  = position_adjusted_risk(lg, "AAPL")
        self.assertEqual(r["position_state"], "risk_free")
        self.assertLess(r["net_at_risk"], 0)
        self.assertGreater(r["pct_recovered"], 100.0)
        self.assertEqual(r["amount_to_recover"], 0.0)


# ── all_positions_adjusted_risk ───────────────────────────────────────────────

class TestAllPositions(unittest.TestCase):
    def setUp(self):
        self.lg = _ledger_with_cash(500_000)
        self.lg.add_trade("AAPL", "buy", 100, 180.0, "2024-01-10")
        self.lg.add_trade("MSFT", "buy",  50, 300.0, "2024-01-10")
        # close MSFT entirely
        self.lg.add_trade("MSFT", "sell", 50, 320.0, "2024-02-01")

    def test_open_only_excludes_closed(self):
        results = all_positions_adjusted_risk(self.lg, open_only=True)
        states  = {r["symbol"]: r["position_state"] for r in results}
        self.assertNotIn("MSFT", states)
        self.assertIn("AAPL", states)

    def test_open_only_false_includes_closed(self):
        results = all_positions_adjusted_risk(self.lg, open_only=False)
        states  = {r["symbol"]: r["position_state"] for r in results}
        self.assertIn("MSFT", states)
        self.assertEqual(states["MSFT"], "closed")

    def test_sorted_by_symbol(self):
        results = all_positions_adjusted_risk(self.lg, open_only=False)
        symbols = [r["symbol"] for r in results]
        self.assertEqual(symbols, sorted(symbols))

    def test_no_position_never_appears(self):
        # "no_position" can't appear: symbols come from trades table
        results = all_positions_adjusted_risk(self.lg, open_only=False)
        for r in results:
            self.assertNotEqual(r["position_state"], "no_position")


if __name__ == "__main__":
    unittest.main()
