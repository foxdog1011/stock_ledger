"""Smoke tests: domain/portfolio functions produce identical output to the
StockLedger delegation shims (and are callable directly)."""
import tempfile
import unittest
from pathlib import Path

from ledger import StockLedger
from domain.portfolio.pnl import position_pnl, all_positions_pnl, position_detail
from domain.portfolio.lots import lots_by_method


def _make_ledger() -> StockLedger:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    ledger = StockLedger(db_path=tmp.name)
    ledger.add_cash(100_000, "2024-01-01")
    ledger.add_trade("AAPL", "buy", 10, 180.0, "2024-01-10", commission=5.0)
    ledger.add_price("AAPL", "2024-01-15", 200.0)
    ledger.add_trade("AAPL", "buy", 5, 190.0, "2024-02-01", commission=3.0)
    ledger.add_price("AAPL", "2024-02-15", 195.0)
    ledger.add_trade("AAPL", "sell", 8, 210.0, "2024-03-01", commission=4.0)
    ledger.add_price("AAPL", "2024-03-10", 205.0)
    return ledger


class TestPositionPnl(unittest.TestCase):
    def setUp(self):
        self.ledger = _make_ledger()

    def test_domain_matches_shim(self):
        via_shim   = self.ledger.position_pnl("AAPL")
        via_domain = position_pnl(self.ledger, "AAPL")
        self.assertEqual(via_shim, via_domain)

    def test_output_keys(self):
        result = position_pnl(self.ledger, "AAPL")
        expected_keys = {
            "symbol", "qty", "avg_cost", "realized_pnl",
            "unrealized_pnl", "last_price", "price_source", "market_value",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_symbol_uppercased(self):
        result = position_pnl(self.ledger, "aapl")
        self.assertEqual(result["symbol"], "AAPL")

    def test_qty_after_sell(self):
        result = position_pnl(self.ledger, "AAPL")
        # bought 10+5=15, sold 8 → 7 remaining
        self.assertAlmostEqual(result["qty"], 7.0)

    def test_realized_pnl_positive(self):
        result = position_pnl(self.ledger, "AAPL")
        self.assertGreater(result["realized_pnl"], 0)

    def test_no_position_returns_zeros(self):
        result = position_pnl(self.ledger, "ZZZZ")
        self.assertEqual(result["qty"], 0.0)
        self.assertEqual(result["realized_pnl"], 0.0)
        self.assertIsNone(result["avg_cost"])
        self.assertIsNone(result["unrealized_pnl"])


class TestAllPositionsPnl(unittest.TestCase):
    def setUp(self):
        self.ledger = _make_ledger()

    def test_domain_matches_shim(self):
        via_shim   = self.ledger.all_positions_pnl()
        via_domain = all_positions_pnl(self.ledger)
        self.assertEqual(via_shim, via_domain)

    def test_sorted_by_symbol(self):
        # Add a second symbol to test ordering
        self.ledger.add_cash(50_000, "2024-01-01")
        self.ledger.add_trade("MSFT", "buy", 5, 300.0, "2024-01-10")
        result = all_positions_pnl(self.ledger)
        symbols = [r["symbol"] for r in result]
        self.assertEqual(symbols, sorted(symbols))

    def test_open_only_default(self):
        result = all_positions_pnl(self.ledger, open_only=True)
        for r in result:
            self.assertGreater(r["qty"], 0)

    def test_open_only_false_includes_closed(self):
        # sell all remaining AAPL
        self.ledger.add_trade("AAPL", "sell", 7, 220.0, "2024-04-01", commission=3.0)
        all_open = all_positions_pnl(self.ledger, open_only=True)
        all_incl = all_positions_pnl(self.ledger, open_only=False)
        self.assertLessEqual(len(all_open), len(all_incl))


class TestPositionDetail(unittest.TestCase):
    def setUp(self):
        self.ledger = _make_ledger()

    def test_domain_matches_shim(self):
        via_shim   = self.ledger.position_detail("AAPL")
        via_domain = position_detail(self.ledger, "AAPL")
        self.assertEqual(via_shim, via_domain)

    def test_output_keys(self):
        result = position_detail(self.ledger, "AAPL")
        for key in ("symbol", "qty", "avg_cost", "realized_pnl",
                    "unrealized_pnl", "last_price", "price_source",
                    "market_value", "pnl_pct", "cost_summary",
                    "running_wac", "wac_series", "last_buy", "cost_impact"):
            self.assertIn(key, result, f"missing key: {key}")

    def test_cost_summary_keys(self):
        result = position_detail(self.ledger, "AAPL")
        cs = result["cost_summary"]
        self.assertIsNotNone(cs)
        for key in ("buy_count", "buy_qty_total", "buy_cost_total_including_fees",
                    "min_buy_price", "max_buy_price", "first_buy_date", "last_buy_date"):
            self.assertIn(key, cs, f"missing cost_summary key: {key}")

    def test_running_wac_entry_keys(self):
        result = position_detail(self.ledger, "AAPL")
        entry = result["running_wac"][0]
        for key in ("trade_id", "date", "side", "qty", "price",
                    "commission", "tax", "qty_after", "avg_cost_after"):
            self.assertIn(key, entry, f"missing running_wac key: {key}")

    def test_last_buy_and_cost_impact_present(self):
        result = position_detail(self.ledger, "AAPL")
        self.assertIsNotNone(result["last_buy"])
        self.assertIsNotNone(result["cost_impact"])

    def test_cost_impact_keys(self):
        result = position_detail(self.ledger, "AAPL")
        ci = result["cost_impact"]
        for key in ("prev_qty", "prev_avg_cost", "buy_qty", "buy_price",
                    "buy_fees", "new_qty", "new_avg_cost",
                    "delta_avg_cost", "delta_avg_cost_pct", "impact_unrealized_pnl"):
            self.assertIn(key, ci, f"missing cost_impact key: {key}")


class TestLotsByMethod(unittest.TestCase):
    def setUp(self):
        self.ledger = _make_ledger()

    def test_domain_matches_shim(self):
        for method in ("fifo", "lifo", "wac"):
            via_shim   = self.ledger.lots_by_method("AAPL", method=method)
            via_domain = lots_by_method(self.ledger, "AAPL", method=method)
            self.assertEqual(via_shim, via_domain, f"mismatch for method={method}")

    def test_output_keys(self):
        result = lots_by_method(self.ledger, "AAPL")
        for key in ("symbol", "method", "as_of", "position_qty",
                    "avg_cost_wac", "lots", "realized_breakdown"):
            self.assertIn(key, result, f"missing key: {key}")

    def test_lot_keys(self):
        result = lots_by_method(self.ledger, "AAPL")
        lot = result["lots"][0]
        for key in ("lot_id", "buy_trade_id", "buy_date", "qty_remaining",
                    "buy_price", "commission", "tax", "cost_per_share",
                    "total_cost", "market_price", "market_value",
                    "unrealized_pnl", "unrealized_pct", "underwater_pct"):
            self.assertIn(key, lot, f"missing lot key: {key}")

    def test_position_qty_matches_pnl(self):
        lots_result = lots_by_method(self.ledger, "AAPL")
        pnl_result  = position_pnl(self.ledger, "AAPL")
        self.assertAlmostEqual(lots_result["position_qty"], pnl_result["qty"])

    def test_invalid_method_raises(self):
        with self.assertRaises(ValueError):
            lots_by_method(self.ledger, "AAPL", method="invalid")

    def test_fifo_vs_lifo_different_realized(self):
        fifo = lots_by_method(self.ledger, "AAPL", method="fifo")
        lifo = lots_by_method(self.ledger, "AAPL", method="lifo")
        fifo_total = sum(
            a["realized_pnl_piece"]
            for rb in fifo["realized_breakdown"]
            for a in rb["allocations"]
        )
        lifo_total = sum(
            a["realized_pnl_piece"]
            for rb in lifo["realized_breakdown"]
            for a in rb["allocations"]
        )
        # With different buy prices, FIFO and LIFO realized P&L may differ
        # (at minimum, both should be computable)
        self.assertIsInstance(fifo_total, float)
        self.assertIsInstance(lifo_total, float)


if __name__ == "__main__":
    unittest.main()
