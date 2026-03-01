"""Unit tests for StockLedger."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger import StockLedger, equity_curve


class TestCash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)

    def test_deposit(self):
        self.ledger.add_cash(1_000_000, date="2024-01-01")
        self.assertAlmostEqual(
            self.ledger.cash_balance(as_of="2024-01-01"), 1_000_000
        )

    def test_withdrawal(self):
        self.ledger.add_cash(1_000_000, date="2024-01-01")
        self.ledger.add_cash(-300_000, date="2024-06-01")
        self.assertAlmostEqual(
            self.ledger.cash_balance(as_of="2024-06-01"), 700_000
        )

    def test_balance_as_of_past_date(self):
        self.ledger.add_cash(1_000_000, date="2024-01-01")
        self.ledger.add_cash(500_000, date="2024-06-01")
        # Before the second deposit
        self.assertAlmostEqual(
            self.ledger.cash_balance(as_of="2024-05-31"), 1_000_000
        )

    def test_zero_amount_raises(self):
        with self.assertRaises(ValueError):
            self.ledger.add_cash(0, date="2024-01-01")


class TestTrades(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)
        self.ledger.add_cash(2_000_000, date="2024-01-01")

    def test_buy_reduces_cash(self):
        self.ledger.add_trade("2330", "buy", qty=1_000, price=580,
                              date="2024-01-15", commission=826)
        expected_cash = 2_000_000 - 1_000 * 580 - 826
        self.assertAlmostEqual(
            self.ledger.cash_balance(as_of="2024-01-15"), expected_cash
        )

    def test_buy_increases_position(self):
        self.ledger.add_trade("2330", "buy", qty=1_000, price=580,
                              date="2024-01-15")
        self.assertAlmostEqual(
            self.ledger.position("2330", as_of="2024-01-15"), 1_000
        )

    def test_sell_increases_cash(self):
        self.ledger.add_trade("2330", "buy", qty=1_000, price=580,
                              date="2024-01-15")
        cash_before = self.ledger.cash_balance(as_of="2024-06-01")
        self.ledger.add_trade("2330", "sell", qty=500, price=900,
                              date="2024-07-01", commission=1_991)
        expected = cash_before + 500 * 900 - 1_991
        self.assertAlmostEqual(
            self.ledger.cash_balance(as_of="2024-07-01"), expected
        )

    def test_sell_decreases_position(self):
        self.ledger.add_trade("2330", "buy", qty=1_000, price=580,
                              date="2024-01-15")
        self.ledger.add_trade("2330", "sell", qty=300, price=700,
                              date="2024-06-01")
        self.assertAlmostEqual(
            self.ledger.position("2330", as_of="2024-06-01"), 700
        )

    def test_insufficient_cash_raises(self):
        with self.assertRaises(ValueError):
            self.ledger.add_trade("2330", "buy", qty=10_000, price=580,
                                  date="2024-01-15")

    def test_insufficient_shares_raises(self):
        self.ledger.add_trade("2330", "buy", qty=100, price=580,
                              date="2024-01-15")
        with self.assertRaises(ValueError):
            self.ledger.add_trade("2330", "sell", qty=200, price=580,
                                  date="2024-02-01")

    def test_invalid_side_raises(self):
        with self.assertRaises(ValueError):
            self.ledger.add_trade("2330", "hold", qty=100, price=580,
                                  date="2024-01-15")

    def test_positions_dict(self):
        self.ledger.add_trade("2330", "buy", qty=1_000, price=580,
                              date="2024-01-15")
        self.ledger.add_trade("2317", "buy", qty=5_000, price=103,
                              date="2024-02-01")
        pos = self.ledger.positions()
        self.assertIn("2330", pos)
        self.assertIn("2317", pos)
        self.assertAlmostEqual(pos["2330"], 1_000)
        self.assertAlmostEqual(pos["2317"], 5_000)

    def test_fully_closed_position_excluded(self):
        self.ledger.add_trade("2330", "buy", qty=500, price=580,
                              date="2024-01-15")
        self.ledger.add_trade("2330", "sell", qty=500, price=700,
                              date="2024-06-01")
        self.assertNotIn("2330", self.ledger.positions())


class TestPrices(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)

    def test_add_and_query_price(self):
        self.ledger.add_price("2330", "2024-01-31", 650)
        self.assertAlmostEqual(
            self.ledger.last_price("2330", as_of="2024-01-31"), 650
        )

    def test_price_falls_back_to_trade(self):
        self.ledger.add_cash(1_000_000, date="2024-01-01")
        self.ledger.add_trade("2330", "buy", qty=100, price=580,
                              date="2024-01-15")
        # No price entry, should fall back to trade price
        self.assertAlmostEqual(
            self.ledger.last_price("2330", as_of="2024-06-01"), 580
        )

    def test_price_not_available_returns_none(self):
        self.assertIsNone(self.ledger.last_price("UNKNOWN", as_of="2024-01-01"))

    def test_price_before_date_returns_none(self):
        self.ledger.add_price("2330", "2024-06-01", 800)
        self.assertIsNone(self.ledger.last_price("2330", as_of="2024-01-01"))


class TestEquitySnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)
        self.ledger.add_cash(2_000_000, date="2024-01-01")
        self.ledger.add_trade("2330", "buy", qty=1_000, price=580,
                              date="2024-01-15")
        self.ledger.add_price("2330", "2024-01-31", 650)

    def test_snapshot_total_equity(self):
        snap = self.ledger.equity_snapshot(as_of="2024-01-31")
        expected_cash = 2_000_000 - 1_000 * 580
        expected_mv = 1_000 * 650
        self.assertAlmostEqual(snap["cash"], expected_cash)
        self.assertAlmostEqual(snap["market_value"], expected_mv)
        self.assertAlmostEqual(snap["total_equity"], expected_cash + expected_mv)


class TestEquityCurve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ledger = StockLedger(db_path=self.tmp.name)
        self.ledger.add_cash(1_000_000, date="2024-01-01")
        self.ledger.add_trade("2330", "buy", qty=500, price=580,
                              date="2024-01-15")
        for d, p in [("2024-01-31", 600), ("2024-02-29", 620),
                     ("2024-03-29", 650)]:
            self.ledger.add_price("2330", d, p)

    def test_curve_shape(self):
        import pandas as pd
        df = equity_curve(self.ledger, "2024-01-31", "2024-03-29", freq="ME")
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn("total_equity", df.columns)
        self.assertIn("cum_return_pct", df.columns)
        self.assertEqual(len(df), 3)

    def test_equity_increases_with_rising_price(self):
        df = equity_curve(self.ledger, "2024-01-31", "2024-03-29", freq="ME")
        self.assertGreater(
            df["total_equity"].iloc[-1],
            df["total_equity"].iloc[0],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
