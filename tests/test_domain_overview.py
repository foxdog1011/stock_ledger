"""Integration tests for domain.overview.service.build_overview."""
import tempfile
import unittest
from pathlib import Path

from ledger import StockLedger
from domain.watchlist.repository import init_watchlist_tables, create_watchlist, add_watchlist_item
from domain.catalyst.repository import init_catalyst_tables, create_catalyst, update_catalyst
from domain.scenario.repository import init_scenario_tables, upsert_scenario
from domain.overview.service import build_overview


# ── helpers ───────────────────────────────────────────────────────────────────

def _empty_ledger() -> tuple[StockLedger, Path]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    lg = StockLedger(db_path=tmp.name)
    p = Path(tmp.name)
    init_watchlist_tables(p)
    init_catalyst_tables(p)
    init_scenario_tables(p)
    return lg, p


def _ledger_with_positions() -> tuple[StockLedger, Path]:
    """Ledger: AAPL 10 shares @ 180, TSLA 5 shares @ 300."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    lg = StockLedger(db_path=tmp.name)
    lg.add_cash(500_000, "2024-01-01")
    lg.add_trade("AAPL", "buy", 10, 180.0, "2024-01-10")
    lg.add_trade("TSLA", "buy",  5, 300.0, "2024-01-10")
    p = Path(tmp.name)
    init_watchlist_tables(p)
    init_catalyst_tables(p)
    init_scenario_tables(p)
    return lg, p


# ── top-level keys contract ───────────────────────────────────────────────────

class TestOverviewKeys(unittest.TestCase):
    def setUp(self):
        self.lg, self.db = _empty_ledger()
        self.result = build_overview(self.db, self.lg, as_of="2025-04-01")

    def test_top_level_keys_present(self):
        for k in ("portfolio", "risk", "watchlist_coverage",
                  "upcoming_catalysts", "offsetting",
                  "generated_at", "as_of"):
            self.assertIn(k, self.result)

    def test_as_of_echoed(self):
        self.assertEqual(self.result["as_of"], "2025-04-01")

    def test_generated_at_format(self):
        # ISO datetime: YYYY-MM-DDTHH:MM:SS
        self.assertRegex(self.result["generated_at"],
                         r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_portfolio_keys(self):
        for k in ("total_equity", "cash", "market_value", "total_cost",
                  "unrealized_pnl", "unrealized_pct", "realized_pnl",
                  "position_count", "as_of"):
            self.assertIn(k, self.result["portfolio"])

    def test_risk_keys(self):
        for k in ("at_risk_count", "risk_free_count",
                  "total_net_at_risk", "positions"):
            self.assertIn(k, self.result["risk"])

    def test_watchlist_coverage_keys(self):
        for k in ("watchlists", "any_insufficient"):
            self.assertIn(k, self.result["watchlist_coverage"])

    def test_upcoming_catalysts_keys(self):
        for k in ("days_window", "count", "items"):
            self.assertIn(k, self.result["upcoming_catalysts"])

    def test_offsetting_keys(self):
        for k in ("losing_count", "total_unrealized_loss",
                  "profit_available", "net_offset_capacity"):
            self.assertIn(k, self.result["offsetting"])


# ── empty ledger ──────────────────────────────────────────────────────────────

class TestEmptyLedger(unittest.TestCase):
    def setUp(self):
        self.lg, self.db = _empty_ledger()
        self.r = build_overview(self.db, self.lg, as_of="2025-04-01")

    def test_portfolio_position_count_zero(self):
        self.assertEqual(self.r["portfolio"]["position_count"], 0)

    def test_portfolio_unrealized_pnl_none_or_zero(self):
        # No positions → sum of empty list → 0.0 (no None items)
        self.assertEqual(self.r["portfolio"]["unrealized_pnl"], 0.0)

    def test_risk_counts_zero(self):
        self.assertEqual(self.r["risk"]["at_risk_count"], 0)
        self.assertEqual(self.r["risk"]["risk_free_count"], 0)

    def test_risk_positions_empty(self):
        self.assertEqual(self.r["risk"]["positions"], [])

    def test_watchlist_coverage_empty(self):
        self.assertEqual(self.r["watchlist_coverage"]["watchlists"], [])
        self.assertFalse(self.r["watchlist_coverage"]["any_insufficient"])

    def test_upcoming_catalysts_empty(self):
        self.assertEqual(self.r["upcoming_catalysts"]["count"], 0)
        self.assertEqual(self.r["upcoming_catalysts"]["items"], [])

    def test_offsetting_zeros(self):
        off = self.r["offsetting"]
        self.assertEqual(off["losing_count"], 0)
        self.assertEqual(off["total_unrealized_loss"], 0.0)


# ── portfolio section ─────────────────────────────────────────────────────────

class TestPortfolioSection(unittest.TestCase):
    def setUp(self):
        self.lg, self.db = _ledger_with_positions()
        self.r = build_overview(self.db, self.lg, as_of="2025-04-01")["portfolio"]

    def test_position_count(self):
        self.assertEqual(self.r["position_count"], 2)

    def test_total_cost_correct(self):
        # AAPL: 10*180 = 1800, TSLA: 5*300 = 1500 → 3300
        self.assertAlmostEqual(self.r["total_cost"], 3300.0)

    def test_cash_positive(self):
        self.assertGreater(self.r["cash"], 0)

    def test_total_equity_equals_cash_plus_market_value(self):
        self.assertAlmostEqual(
            self.r["total_equity"],
            self.r["cash"] + self.r["market_value"],
        )

    def test_unrealized_pnl_is_float_or_none(self):
        u = self.r["unrealized_pnl"]
        self.assertTrue(u is None or isinstance(u, float))

    def test_unrealized_pct_none_when_pnl_none(self):
        # If pnl is None, pct must also be None
        if self.r["unrealized_pnl"] is None:
            self.assertIsNone(self.r["unrealized_pct"])


# ── risk section ──────────────────────────────────────────────────────────────

class TestRiskSection(unittest.TestCase):
    def setUp(self):
        self.lg, self.db = _ledger_with_positions()
        self.r = build_overview(self.db, self.lg, as_of="2025-04-01")["risk"]

    def test_positions_count_matches_open_positions(self):
        self.assertEqual(len(self.r["positions"]), 2)

    def test_position_item_keys(self):
        for p in self.r["positions"]:
            for k in ("symbol", "position_state", "net_at_risk", "pct_recovered"):
                self.assertIn(k, p)

    def test_at_risk_plus_risk_free_equals_total(self):
        total = self.r["at_risk_count"] + self.r["risk_free_count"]
        self.assertEqual(total, len(self.r["positions"]))

    def test_position_state_values_valid(self):
        valid = {"risk_free", "at_risk"}
        for p in self.r["positions"]:
            self.assertIn(p["position_state"], valid)


# ── watchlist coverage section ────────────────────────────────────────────────

class TestWatchlistCoverageSection(unittest.TestCase):
    def setUp(self):
        self.lg, self.db = _ledger_with_positions()

    def test_no_watchlists(self):
        r = build_overview(self.db, self.lg, as_of="2025-04-01")
        self.assertEqual(r["watchlist_coverage"]["watchlists"], [])
        self.assertFalse(r["watchlist_coverage"]["any_insufficient"])

    def test_insufficient_watchlist_sets_flag(self):
        create_watchlist(self.db, "Main")
        r = build_overview(self.db, self.lg, as_of="2025-04-01")
        wl = r["watchlist_coverage"]["watchlists"]
        self.assertEqual(len(wl), 1)
        self.assertFalse(wl[0]["coverage_sufficient"])
        self.assertTrue(r["watchlist_coverage"]["any_insufficient"])

    def test_sufficient_watchlist_clears_flag(self):
        wl = create_watchlist(self.db, "Main")
        for i in range(6):  # 2 positions × 3 = 6 required
            add_watchlist_item(self.db, wl["id"], f"SYM{i}")
        r = build_overview(self.db, self.lg, as_of="2025-04-01")
        cov = r["watchlist_coverage"]["watchlists"][0]
        self.assertTrue(cov["coverage_sufficient"])
        self.assertFalse(r["watchlist_coverage"]["any_insufficient"])

    def test_multiple_watchlists_any_insufficient(self):
        wl1 = create_watchlist(self.db, "Full")
        wl2 = create_watchlist(self.db, "Empty")
        for i in range(6):
            add_watchlist_item(self.db, wl1["id"], f"SYM{i}")
        r = build_overview(self.db, self.lg, as_of="2025-04-01")
        self.assertTrue(r["watchlist_coverage"]["any_insufficient"])
        self.assertEqual(len(r["watchlist_coverage"]["watchlists"]), 2)


# ── upcoming catalysts section ────────────────────────────────────────────────

class TestUpcomingCatalystsSection(unittest.TestCase):
    def setUp(self):
        self.lg, self.db = _empty_ledger()

    def test_no_catalysts(self):
        r = build_overview(self.db, self.lg, as_of="2025-04-01")
        uc = r["upcoming_catalysts"]
        self.assertEqual(uc["count"], 0)
        self.assertEqual(uc["items"], [])

    def test_catalyst_in_range_appears(self):
        create_catalyst(self.db, "company", "Earnings", event_date="2025-04-10")
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=30)
        self.assertEqual(r["upcoming_catalysts"]["count"], 1)

    def test_catalyst_outside_range_excluded(self):
        create_catalyst(self.db, "company", "Far future", event_date="2025-06-01")
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=30)
        self.assertEqual(r["upcoming_catalysts"]["count"], 0)

    def test_catalyst_days_zero_same_day_only(self):
        create_catalyst(self.db, "macro", "Today", event_date="2025-04-01")
        create_catalyst(self.db, "macro", "Tomorrow", event_date="2025-04-02")
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=0)
        self.assertEqual(r["upcoming_catalysts"]["count"], 1)
        self.assertEqual(r["upcoming_catalysts"]["days_window"], 0)

    def test_has_scenario_true_when_present(self):
        c = create_catalyst(self.db, "company", "Earnings", event_date="2025-04-10")
        upsert_scenario(self.db, c["id"], {"plan_a": "Buy"})
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=30)
        self.assertTrue(r["upcoming_catalysts"]["items"][0]["has_scenario"])

    def test_has_scenario_false_when_absent(self):
        create_catalyst(self.db, "company", "Earnings", event_date="2025-04-10")
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=30)
        self.assertFalse(r["upcoming_catalysts"]["items"][0]["has_scenario"])

    def test_passed_catalyst_not_included(self):
        c = create_catalyst(self.db, "company", "Done", event_date="2025-04-10")
        update_catalyst(self.db, c["id"], {"status": "passed"})
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=30)
        self.assertEqual(r["upcoming_catalysts"]["count"], 0)

    def test_item_keys_present(self):
        create_catalyst(self.db, "macro", "Rate", event_date="2025-04-10")
        r = build_overview(self.db, self.lg, as_of="2025-04-01", catalyst_days=30)
        item = r["upcoming_catalysts"]["items"][0]
        for k in ("id", "event_type", "symbol", "title", "event_date", "has_scenario"):
            self.assertIn(k, item)


# ── offsetting section ────────────────────────────────────────────────────────

class TestOffsettingSection(unittest.TestCase):
    def test_all_positions_profitable_no_losses(self):
        # Buy at 100, add a high quote so unrealized > 0
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        lg = StockLedger(db_path=tmp.name)
        lg.add_cash(100_000, "2024-01-01")
        lg.add_trade("AAPL", "buy", 10, 100.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-11", 200.0)  # unrealized gain
        db = Path(tmp.name)
        init_watchlist_tables(db)
        init_catalyst_tables(db)
        init_scenario_tables(db)
        r = build_overview(db, lg, as_of="2024-01-11")["offsetting"]
        self.assertEqual(r["losing_count"], 0)
        self.assertEqual(r["total_unrealized_loss"], 0.0)

    def test_losing_position_counted(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        lg = StockLedger(db_path=tmp.name)
        lg.add_cash(100_000, "2024-01-01")
        lg.add_trade("AAPL", "buy", 10, 200.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-11", 100.0)  # unrealized loss
        db = Path(tmp.name)
        init_watchlist_tables(db)
        init_catalyst_tables(db)
        init_scenario_tables(db)
        r = build_overview(db, lg, as_of="2024-01-11")["offsetting"]
        self.assertEqual(r["losing_count"], 1)
        self.assertLess(r["total_unrealized_loss"], 0.0)  # must be negative

    def test_net_offset_capacity_formula(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        lg = StockLedger(db_path=tmp.name)
        lg.add_cash(100_000, "2024-01-01")
        lg.add_trade("AAPL", "buy", 10, 200.0, "2024-01-10")
        lg.add_price("AAPL", "2024-01-11", 100.0)
        db = Path(tmp.name)
        init_watchlist_tables(db)
        init_catalyst_tables(db)
        init_scenario_tables(db)
        r = build_overview(db, lg, as_of="2024-01-11")["offsetting"]
        expected = r["profit_available"] + r["total_unrealized_loss"]
        self.assertAlmostEqual(r["net_offset_capacity"], expected)


# ── as_of default ─────────────────────────────────────────────────────────────

class TestAsOfDefault(unittest.TestCase):
    def test_as_of_defaults_to_today(self):
        import datetime
        lg, db = _empty_ledger()
        r = build_overview(db, lg)
        self.assertEqual(r["as_of"], datetime.date.today().isoformat())


if __name__ == "__main__":
    unittest.main()
