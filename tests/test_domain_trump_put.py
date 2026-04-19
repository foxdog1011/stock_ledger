"""Tests for domain.trump_put — scoring, thresholds, backtest, fetcher."""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from domain.trump_put.scoring import compute_composite, WEIGHTS, LABELS
from domain.trump_put.thresholds import classify, get_all_thresholds
from domain.trump_put.backtest import compute_backtest, to_json
from domain.trump_put.models import (
    BacktestPair,
    BacktestResult,
    HistoricalEvent,
)
from domain.trump_put.fetcher import MarketDataFetcher


# ── Scoring ──────────────────────────────────────────────────────────────────


class TestComputeComposite(unittest.TestCase):
    """Tests for compute_composite weighted scoring."""

    def test_all_neutral_score_near_zero(self):
        score, label = compute_composite(sp500=0, tnx=0, vix=0, dxy=0, approval=0)
        self.assertEqual(score, 0)
        self.assertEqual(label, "Dormant")

    def test_all_max_score_is_100(self):
        score, label = compute_composite(
            sp500=100, tnx=100, vix=100, dxy=100, approval=100
        )
        self.assertEqual(score, 100)
        self.assertEqual(label, "Activated")

    def test_sp500_at_pain_threshold_elevated(self):
        # sp500 component high (85), others neutral
        score, _ = compute_composite(sp500=85, tnx=0, vix=0, dxy=0, approval=0)
        # 85 * 0.30 / 1.0 = 25.5 -> 26
        self.assertGreater(score, 20)

    def test_vix_spike_elevated(self):
        # VIX component high, others at 0
        score, _ = compute_composite(sp500=0, tnx=0, vix=80, dxy=0, approval=0)
        # 80 * 0.15 / 1.0 = 12
        self.assertGreater(score, 10)

    def test_multiple_high_indicators(self):
        score, label = compute_composite(
            sp500=85, tnx=80, vix=55, dxy=30, approval=45
        )
        # weighted sum should be in High Alert or Activated range
        self.assertGreaterEqual(score, 60)

    def test_no_data_returns_zero(self):
        score, label = compute_composite()
        self.assertEqual(score, 0)
        self.assertEqual(label, "No Data")

    def test_all_none_returns_no_data(self):
        score, label = compute_composite(
            sp500=None, tnx=None, vix=None, dxy=None, approval=None
        )
        self.assertEqual(score, 0)
        self.assertEqual(label, "No Data")

    def test_partial_none_uses_available(self):
        # Only sp500 provided; weight renormalized
        score, _ = compute_composite(sp500=50, tnx=None, vix=None)
        # 50 * 0.30 / 0.30 = 50
        self.assertEqual(score, 50)

    def test_unknown_indicator_ignored(self):
        score, _ = compute_composite(sp500=50, bogus=100)
        # bogus not in WEIGHTS, so only sp500 counted
        self.assertEqual(score, 50)

    def test_score_clamped_to_100(self):
        # Even if raw > 100 (shouldn't happen, but boundary)
        score, _ = compute_composite(sp500=200)
        self.assertEqual(score, 100)

    def test_score_clamped_to_0(self):
        score, _ = compute_composite(sp500=-50)
        self.assertEqual(score, 0)

    def test_label_boundaries(self):
        """Each label boundary maps correctly."""
        cases = [
            (0, "Dormant"), (20, "Dormant"),
            (21, "Watchful"), (40, "Watchful"),
            (41, "Elevated"), (60, "Elevated"),
            (61, "High Alert"), (80, "High Alert"),
            (81, "Activated"), (100, "Activated"),
        ]
        for target, expected_label in cases:
            score, label = compute_composite(sp500=target)
            self.assertEqual(label, expected_label, f"score={target}")


# ── Thresholds ───────────────────────────────────────────────────────────────


class TestClassify(unittest.TestCase):
    """Tests for threshold zone classification."""

    def test_sp500_above_election_level(self):
        zone, score = classify("sp500", 6000.0)
        self.assertEqual(zone, "Above Election Day")
        self.assertEqual(score, 0)

    def test_sp500_at_put_activation(self):
        zone, score = classify("sp500", 4900.0)
        self.assertEqual(zone, "Trump Put Activated (BofA)")
        self.assertEqual(score, 85)

    def test_sp500_deep_crisis(self):
        zone, score = classify("sp500", 4500.0)
        self.assertEqual(zone, "Deep Crisis")
        self.assertEqual(score, 100)

    def test_sp500_media_pressure(self):
        zone, score = classify("sp500", 5500.0)
        self.assertEqual(zone, "Media Pressure Zone")
        self.assertEqual(score, 20)

    def test_tnx_danger_zone(self):
        zone, score = classify("tnx", 4.6)
        self.assertEqual(zone, "Danger (April 2025 trigger)")
        self.assertEqual(score, 80)

    def test_tnx_bond_crisis(self):
        zone, score = classify("tnx", 5.5)
        self.assertEqual(zone, "Bond Crisis")
        self.assertEqual(score, 100)

    def test_tnx_low_calm(self):
        zone, score = classify("tnx", 3.0)
        self.assertEqual(zone, "Low / Calm")
        self.assertEqual(score, 0)

    def test_vix_extreme(self):
        zone, score = classify("vix", 45.0)
        self.assertEqual(zone, "Extreme (2025 crisis level)")
        self.assertEqual(score, 80)

    def test_vix_calm(self):
        zone, score = classify("vix", 12.0)
        self.assertEqual(zone, "Calm")
        self.assertEqual(score, 0)

    def test_dxy_strong(self):
        zone, score = classify("dxy", 102.0)
        self.assertEqual(zone, "Strong")
        self.assertEqual(score, 30)

    def test_approval_deeply_unpopular(self):
        zone, score = classify("approval", 30.0)
        self.assertEqual(zone, "Deeply Unpopular")
        self.assertEqual(score, 100)

    def test_approval_popular(self):
        zone, score = classify("approval", 55.0)
        self.assertEqual(zone, "Popular")
        self.assertEqual(score, 0)

    def test_unknown_indicator(self):
        zone, score = classify("gold", 2000.0)
        self.assertEqual(zone, "Unknown")
        self.assertEqual(score, 0)


class TestGetAllThresholds(unittest.TestCase):
    def test_returns_all_indicators(self):
        result = get_all_thresholds()
        expected_minimum = {"sp500", "tnx", "vix", "dxy", "approval"}
        self.assertTrue(
            expected_minimum.issubset(set(result.keys())),
            f"Missing indicators: {expected_minimum - set(result.keys())}",
        )

    def test_each_zone_has_required_fields(self):
        result = get_all_thresholds()
        for indicator, zones in result.items():
            for z in zones:
                self.assertIn("lower", z)
                self.assertIn("upper", z)
                self.assertIn("zone", z)
                self.assertIn("score", z)


# ── Backtest ─────────────────────────────────────────────────────────────────


class TestComputeBacktest(unittest.TestCase):
    """Tests for backtest logic using real EVENTS data."""

    def test_pairs_not_empty(self):
        result = compute_backtest()
        self.assertGreater(len(result.pairs), 0)

    def test_pairs_have_positive_days(self):
        result = compute_backtest()
        for p in result.pairs:
            self.assertGreater(p.days, 0)

    def test_avg_days_to_reversal_positive(self):
        result = compute_backtest()
        self.assertGreater(result.avg_days_to_reversal, 0)

    def test_hit_rate_denominator_matches_filter(self):
        """Regression: denominator must equal the number of pairs with days<=30."""
        result = compute_backtest()
        pairs_within_30d = [p for p in result.pairs if p.days <= 30]
        for key, hr in result.hit_rates.items():
            self.assertEqual(
                hr["total_escalations"],
                len(pairs_within_30d),
                "total_escalations should equal count of pairs with days<=30",
            )
            self.assertEqual(hr["reversed_within_30d"], len(pairs_within_30d))

    def test_hit_rate_is_100_when_filtered_consistently(self):
        """When numerator and denominator match the same filter, rate is 100."""
        result = compute_backtest()
        for key, hr in result.hit_rates.items():
            if hr["total_escalations"] > 0:
                self.assertEqual(hr["hit_rate"], 100.0)

    def test_drawdown_pct_calculated(self):
        result = compute_backtest()
        pairs_with_sp500 = [
            p for p in result.pairs
            if p.sp500_at_escalation and p.sp500_at_reversal
        ]
        for p in pairs_with_sp500:
            expected = round(
                (p.sp500_at_reversal - p.sp500_at_escalation)
                / p.sp500_at_escalation * 100, 2
            )
            self.assertEqual(p.drawdown_pct, expected)

    def test_prediction_at_high_score(self):
        result = compute_backtest(current_score=70)
        self.assertIsNotNone(result.current_prediction)
        self.assertIn("70", result.current_prediction)

    def test_prediction_at_moderate_score(self):
        result = compute_backtest(current_score=45)
        self.assertIsNotNone(result.current_prediction)
        self.assertIn("45", result.current_prediction)

    def test_no_prediction_at_low_score(self):
        result = compute_backtest(current_score=10)
        self.assertIsNone(result.current_prediction)


class TestBacktestKnownPairs(unittest.TestCase):
    """Verify known escalation-to-reversal pairs produce correct days."""

    def test_feb_tariff_pair(self):
        """Feb 1 escalation -> Feb 4 reversal = 3 days."""
        result = compute_backtest()
        feb_pair = next(
            (p for p in result.pairs if p.escalation_date == "2025-02-01"),
            None,
        )
        self.assertIsNotNone(feb_pair)
        self.assertEqual(feb_pair.days, 3)
        self.assertEqual(feb_pair.reversal_date, "2025-02-04")

    def test_liberation_day_pair(self):
        """Apr 2 escalation -> Apr 9 reversal = 7 days."""
        result = compute_backtest()
        apr_pair = next(
            (p for p in result.pairs if p.escalation_date == "2025-04-02"),
            None,
        )
        self.assertIsNotNone(apr_pair)
        self.assertEqual(apr_pair.days, 7)
        self.assertEqual(apr_pair.reversal_date, "2025-04-09")


class TestToJson(unittest.TestCase):
    def test_serializes_all_fields(self):
        result = compute_backtest()
        data = to_json(result)
        self.assertIn("pairs", data)
        self.assertIn("avg_days_to_reversal", data)
        self.assertIn("hit_rates", data)
        self.assertIn("current_prediction", data)

    def test_pairs_are_dicts(self):
        result = compute_backtest()
        data = to_json(result)
        for p in data["pairs"]:
            self.assertIsInstance(p, dict)
            self.assertIn("escalation_date", p)
            self.assertIn("days", p)


# ── Fetcher ──────────────────────────────────────────────────────────────────


class TestMarketDataFetcher(unittest.TestCase):
    """Tests for the MarketDataFetcher fallback chain."""

    def setUp(self):
        self.fetcher = MarketDataFetcher(cache_ttl=300)

    def test_unknown_indicator_returns_none(self):
        result = self.fetcher.fetch("gold")
        self.assertIsNone(result)

    @patch("domain.trump_put.fetcher._fetch_polygon", return_value=None)
    @patch("domain.trump_put.fetcher._fetch_fred", return_value=None)
    def test_yfinance_failure_falls_back_to_fred(
        self, mock_fred, mock_polygon
    ):
        mock_fred.return_value = (4.35, "2025-04-01")

        with patch.dict("sys.modules", {"yfinance": MagicMock()}):
            yf_mock = MagicMock()
            yf_mock.Ticker.return_value.history.return_value = MagicMock(
                empty=True
            )
            with patch.dict("sys.modules", {"yfinance": yf_mock}):
                result = self.fetcher.fetch("tnx")

        # FRED should have been called since yfinance returned empty
        self.assertTrue(mock_fred.called)

    @patch("domain.trump_put.fetcher._fetch_polygon", return_value=None)
    @patch("domain.trump_put.fetcher._fetch_fred", return_value=None)
    def test_all_sources_fail_returns_none_or_stale(
        self, mock_fred, mock_polygon
    ):
        with patch.dict("sys.modules", {"yfinance": MagicMock()}):
            yf_mock = MagicMock()
            yf_mock.Ticker.return_value.history.return_value = MagicMock(
                empty=True
            )
            with patch.dict("sys.modules", {"yfinance": yf_mock}):
                result = self.fetcher.fetch("sp500")

        # No stale cache, all sources failed -> None
        self.assertIsNone(result)

    @patch("domain.trump_put.fetcher._fetch_polygon", return_value=None)
    @patch("domain.trump_put.fetcher._fetch_fred", return_value=None)
    def test_stale_cache_returned_when_all_fail(
        self, mock_fred, mock_polygon
    ):
        # Pre-populate cache with stale entry
        import time

        self.fetcher._store_cache("sp500", 5500.0, "2025-04-01")
        # Make it stale by backdating fetched_at
        with self.fetcher._lock:
            self.fetcher._cache["sp500"].fetched_at = time.time() - 999

        with patch.dict("sys.modules", {"yfinance": MagicMock()}):
            yf_mock = MagicMock()
            yf_mock.Ticker.return_value.history.return_value = MagicMock(
                empty=True
            )
            with patch.dict("sys.modules", {"yfinance": yf_mock}):
                result = self.fetcher.fetch("sp500")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], 5500.0)

    def test_cache_hit_skips_network(self):
        self.fetcher._store_cache("vix", 25.0, "2025-04-15")
        result = self.fetcher.fetch("vix")
        self.assertEqual(result, (25.0, "2025-04-15"))

    @patch("domain.trump_put.fetcher._fetch_polygon")
    def test_polygon_success_stores_cache(self, mock_polygon):
        mock_polygon.return_value = (5800.0, "2025-04-15")
        result = self.fetcher.fetch("sp500")
        self.assertEqual(result, (5800.0, "2025-04-15"))
        # Verify it's cached
        cached = self.fetcher._check_cache("sp500")
        self.assertIsNotNone(cached)

    def test_fetch_all_returns_dict(self):
        # Pre-cache all indicators
        for key in ("sp500", "tnx", "vix", "dxy"):
            self.fetcher._store_cache(key, 100.0, "2025-04-15")
        results = self.fetcher.fetch_all()
        self.assertEqual(len(results), 4)


if __name__ == "__main__":
    unittest.main()
