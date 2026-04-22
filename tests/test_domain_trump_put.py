"""Tests for domain.trump_put — scoring, thresholds, backtest, fetcher, formatter, tariffs, historical, service, etc."""
from __future__ import annotations

import math
import time
import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from domain.trump_put.scoring import (
    compute_composite, WEIGHTS, LABELS,
    rolling_z_score, compute_rolling_z_composite, generate_narrative,
)
from domain.trump_put.thresholds import classify, get_all_thresholds
from domain.trump_put.backtest import compute_backtest, to_json
from domain.trump_put.models import (
    BacktestPair,
    BacktestResult,
    HistoricalEvent,
    IndicatorReading,
    TrumpPutReport,
)
from domain.trump_put.fetcher import MarketDataFetcher
from domain.trump_put.formatter import (
    _gauge, _fmt_value, _zone_emoji,
    format_discord, format_plain, to_json as formatter_to_json,
)
from domain.trump_put.tariffs import load_tariffs, get_summary
from domain.trump_put.historical import get_nearby_events, EVENTS
from domain.trump_put.discord_alert import should_alert


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


# ── Rolling Z-Score ─────────────────────────────────────────────────────────


class TestRollingZScore(unittest.TestCase):
    """Tests for rolling_z_score function."""

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(rolling_z_score([]))
        self.assertIsNone(rolling_z_score([42.0]))

    def test_constant_series_returns_zero(self):
        result = rolling_z_score([5.0, 5.0, 5.0, 5.0, 5.0])
        self.assertEqual(result, 0.0)

    def test_positive_z_for_high_outlier(self):
        # Last value is much higher than the mean
        values = [10.0] * 20 + [20.0]
        z = rolling_z_score(values)
        self.assertIsNotNone(z)
        self.assertGreater(z, 0)

    def test_negative_z_for_low_outlier(self):
        values = [10.0] * 20 + [0.0]
        z = rolling_z_score(values)
        self.assertIsNotNone(z)
        self.assertLess(z, 0)

    def test_window_parameter(self):
        # With window=3, only last 3 values are used
        values = [100.0, 100.0, 100.0, 10.0, 10.0, 10.0]
        z_full = rolling_z_score(values, window=len(values))
        z_short = rolling_z_score(values, window=3)
        # With window=3 (all 10s), z should be 0
        self.assertEqual(z_short, 0.0)

    def test_two_values_computes(self):
        z = rolling_z_score([0.0, 10.0])
        self.assertIsNotNone(z)
        self.assertGreater(z, 0)


# ── Rolling Z Composite ────────────────────────────────────────────────────


class TestComputeRollingZComposite(unittest.TestCase):
    """Tests for compute_rolling_z_composite."""

    def test_empty_histories_returns_none(self):
        result = compute_rolling_z_composite({})
        self.assertIsNone(result)

    def test_unknown_indicator_ignored(self):
        result = compute_rolling_z_composite({"gold": [1.0, 2.0, 3.0]})
        self.assertIsNone(result)

    def test_single_indicator_returns_score_and_label(self):
        # Constant series -> z=0 -> score near 0
        history = [100.0] * 50 + [100.0]
        result = compute_rolling_z_composite({"sp500": history})
        self.assertIsNotNone(result)
        score, label = result
        self.assertEqual(score, 0)
        self.assertEqual(label, "Dormant")

    def test_sp500_drop_causes_stress(self):
        # S&P falling = negative Z = stress for sp500
        history = [5800.0] * 50 + [5000.0]
        result = compute_rolling_z_composite({"sp500": history})
        self.assertIsNotNone(result)
        score, _ = result
        self.assertGreater(score, 0)

    def test_vix_spike_causes_stress(self):
        # VIX rising = positive Z = stress
        history = [15.0] * 50 + [50.0]
        result = compute_rolling_z_composite({"vix": history})
        self.assertIsNotNone(result)
        score, _ = result
        self.assertGreater(score, 0)

    def test_multiple_indicators(self):
        histories = {
            "sp500": [5800.0] * 50 + [5000.0],
            "vix": [15.0] * 50 + [50.0],
            "tnx": [4.0] * 50 + [5.0],
        }
        result = compute_rolling_z_composite(histories)
        self.assertIsNotNone(result)
        score, label = result
        self.assertGreater(score, 20)

    def test_insufficient_data_for_indicator_skipped(self):
        histories = {
            "sp500": [100.0],  # too few for z-score
            "vix": [15.0] * 50 + [50.0],  # enough data
        }
        result = compute_rolling_z_composite(histories)
        self.assertIsNotNone(result)


# ── Generate Narrative ──────────────────────────────────────────────────────


class TestGenerateNarrative(unittest.TestCase):
    """Tests for the fallback narrative generator in scoring.py."""

    def _make_report(self, score: int, label: str, **kwargs) -> TrumpPutReport:
        return TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=kwargs.get("sp500"),
            tnx=kwargs.get("tnx"),
            vix=kwargs.get("vix"),
            dxy=kwargs.get("dxy"),
            approval=kwargs.get("approval"),
            composite_score=score,
            composite_label=label,
            narrative="",
            nearby_events=[],
            thresholds={},
        )

    def test_dormant_narrative(self):
        report = self._make_report(10, "Dormant")
        text = generate_narrative(report)
        self.assertIn("dormant", text.lower())

    def test_activated_narrative(self):
        sp500 = IndicatorReading("sp500", "S&P 500", 4900.0, "2025-04-15",
                                 "Trump Put Activated (BofA)", 85)
        report = self._make_report(85, "Activated", sp500=sp500)
        text = generate_narrative(report)
        self.assertIn("activation", text.lower())
        self.assertIn("4,900.00", text)

    def test_elevated_narrative(self):
        report = self._make_report(45, "Elevated")
        text = generate_narrative(report)
        self.assertIn("Elevated", text)

    def test_high_alert_narrative(self):
        report = self._make_report(65, "High Alert")
        text = generate_narrative(report)
        self.assertIn("pain threshold", text.lower())

    def test_watchful_narrative(self):
        report = self._make_report(25, "Watchful")
        text = generate_narrative(report)
        self.assertIn("mild pressure", text.lower())

    def test_all_indicators_present(self):
        sp500 = IndicatorReading("sp500", "S&P 500", 5500.0, "2025-04-15", "Media Pressure Zone", 20)
        tnx = IndicatorReading("tnx", "10Y Treasury", 4.35, "2025-04-15", "Warning", 55)
        vix = IndicatorReading("vix", "VIX", 25.0, "2025-04-15", "Elevated", 30)
        dxy = IndicatorReading("dxy", "US Dollar Index", 103.0, "2025-04-15", "Strong", 30)
        appr = IndicatorReading("approval", "Trump Approval", 42.0, "2025-04-15", "Weak", 45)
        report = self._make_report(
            45, "Elevated",
            sp500=sp500, tnx=tnx, vix=vix, dxy=dxy, approval=appr,
        )
        text = generate_narrative(report)
        self.assertIn("S&P 500", text)
        self.assertIn("10Y yield", text)
        self.assertIn("VIX", text)
        self.assertIn("DXY", text)
        self.assertIn("Approval", text)

    def test_no_indicators_returns_fallback(self):
        report = self._make_report(0, "Dormant")
        text = generate_narrative(report)
        self.assertIn("No market data available", text)


# ── Formatter ───────────────────────────────────────────────────────────────


class TestGauge(unittest.TestCase):
    def test_zero_score(self):
        result = _gauge(0)
        self.assertIn("0/100", result)
        self.assertIn("\u2591" * 10, result)

    def test_full_score(self):
        result = _gauge(100)
        self.assertIn("100/100", result)
        self.assertIn("\u2588" * 10, result)

    def test_mid_score(self):
        result = _gauge(50)
        self.assertIn("50/100", result)


class TestFmtValue(unittest.TestCase):
    def test_sp500_format(self):
        r = IndicatorReading("sp500", "S&P 500", 5783.42, "2025-04-15", "Zone", 0)
        self.assertEqual(_fmt_value(r), "5,783.42")

    def test_tnx_format(self):
        r = IndicatorReading("tnx", "10Y", 4.352, "2025-04-15", "Zone", 0)
        self.assertEqual(_fmt_value(r), "4.352%")

    def test_approval_format(self):
        r = IndicatorReading("approval", "Approval", 42.5, "2025-04-15", "Zone", 0)
        self.assertEqual(_fmt_value(r), "42.5%")

    def test_other_format(self):
        r = IndicatorReading("vix", "VIX", 25.123, "2025-04-15", "Zone", 0)
        self.assertEqual(_fmt_value(r), "25.12")


class TestZoneEmoji(unittest.TestCase):
    def test_green_zone(self):
        self.assertEqual(_zone_emoji(0), "\U0001f7e2")
        self.assertEqual(_zone_emoji(20), "\U0001f7e2")

    def test_yellow_zone(self):
        self.assertEqual(_zone_emoji(21), "\U0001f7e1")
        self.assertEqual(_zone_emoji(40), "\U0001f7e1")

    def test_orange_zone(self):
        self.assertEqual(_zone_emoji(41), "\U0001f7e0")
        self.assertEqual(_zone_emoji(60), "\U0001f7e0")

    def test_red_zone(self):
        self.assertEqual(_zone_emoji(61), "\U0001f534")
        self.assertEqual(_zone_emoji(100), "\U0001f534")


class TestFormatDiscord(unittest.TestCase):
    def _make_report(self, score: int = 50) -> TrumpPutReport:
        sp500 = IndicatorReading("sp500", "S&P 500", 5500.0, "2025-04-15",
                                 "Media Pressure Zone", 20)
        tnx = IndicatorReading("tnx", "10Y Treasury", 4.35, "2025-04-15",
                               "Warning", 55)
        return TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=sp500,
            tnx=tnx,
            vix=None,
            dxy=None,
            approval=None,
            composite_score=score,
            composite_label="Elevated",
            narrative="Test narrative.",
            nearby_events=[
                HistoricalEvent(date(2025, 4, 9), 5457.0, 4.34,
                                "90-day tariff pause", "reversal"),
            ],
            thresholds={},
        )

    def test_contains_header(self):
        text = format_discord(self._make_report())
        self.assertIn("Trump Put Tracker", text)
        self.assertIn("2025-04-15", text)

    def test_contains_composite_score(self):
        text = format_discord(self._make_report())
        self.assertIn("50/100", text)
        self.assertIn("Elevated", text)

    def test_contains_indicator_table(self):
        text = format_discord(self._make_report())
        self.assertIn("Indicator", text)
        self.assertIn("S&P 500", text)
        self.assertIn("10Y Treasury", text)

    def test_contains_narrative(self):
        text = format_discord(self._make_report())
        self.assertIn("Test narrative.", text)

    def test_contains_historical_context(self):
        text = format_discord(self._make_report())
        self.assertIn("Historical Context", text)
        self.assertIn("90-day tariff pause", text)

    def test_truncates_long_output(self):
        """Output should be truncated to 1950 chars max."""
        report = self._make_report()
        # Even with few indicators, should not exceed limit
        text = format_discord(report)
        self.assertLessEqual(len(text), 1950)

    def test_none_indicators_skipped(self):
        report = self._make_report()
        text = format_discord(report)
        # VIX, DXY, approval are None — should not appear
        self.assertNotIn("VIX", text.split("Thresholds")[0])


class TestFormatPlain(unittest.TestCase):
    def _make_report(self) -> TrumpPutReport:
        sp500 = IndicatorReading("sp500", "S&P 500", 5500.0, "2025-04-15",
                                 "Media Pressure Zone", 20)
        return TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=sp500,
            tnx=None, vix=None, dxy=None, approval=None,
            composite_score=30,
            composite_label="Watchful",
            narrative="Plain test.",
            nearby_events=[
                HistoricalEvent(date(2025, 4, 2), 5670.0, 4.20,
                                "Liberation Day", "escalation"),
            ],
            thresholds={},
        )

    def test_contains_header(self):
        text = format_plain(self._make_report())
        self.assertIn("Trump Put Tracker", text)

    def test_contains_score(self):
        text = format_plain(self._make_report())
        self.assertIn("30/100", text)
        self.assertIn("Watchful", text)

    def test_contains_indicator(self):
        text = format_plain(self._make_report())
        self.assertIn("S&P 500", text)

    def test_contains_narrative(self):
        text = format_plain(self._make_report())
        self.assertIn("Plain test.", text)

    def test_contains_historical(self):
        text = format_plain(self._make_report())
        self.assertIn("Liberation Day", text)


class TestFormatterToJson(unittest.TestCase):
    def _make_report(self) -> TrumpPutReport:
        sp500 = IndicatorReading("sp500", "S&P 500", 5500.0, "2025-04-15",
                                 "Media Pressure Zone", 20)
        return TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=sp500,
            tnx=None, vix=None, dxy=None, approval=None,
            composite_score=30,
            composite_label="Watchful",
            narrative="JSON test.",
            nearby_events=[
                HistoricalEvent(date(2025, 4, 9), 5457.0, 4.34,
                                "90-day pause", "reversal"),
            ],
            thresholds={"sp500": [{"lower": 0, "upper": 99999, "zone": "Test", "score": 0}]},
        )

    def test_basic_fields(self):
        data = formatter_to_json(self._make_report())
        self.assertIn("timestamp", data)
        self.assertEqual(data["composite_score"], 30)
        self.assertEqual(data["composite_label"], "Watchful")
        self.assertEqual(data["narrative"], "JSON test.")

    def test_indicators_present(self):
        data = formatter_to_json(self._make_report())
        indicators = data["indicators"]
        self.assertIsNotNone(indicators["sp500"])
        self.assertEqual(indicators["sp500"]["value"], 5500.0)
        self.assertIsNone(indicators["tnx"])

    def test_nearby_events_serialized(self):
        data = formatter_to_json(self._make_report())
        events = data["nearby_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["description"], "90-day pause")

    def test_rolling_z_included_when_present(self):
        report = TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=None, tnx=None, vix=None, dxy=None, approval=None,
            composite_score=0, composite_label="No Data",
            narrative="", nearby_events=[], thresholds={},
            rolling_z_composite=(45, "Elevated"),
        )
        data = formatter_to_json(report)
        self.assertEqual(data["rolling_z_composite"]["score"], 45)
        self.assertEqual(data["rolling_z_composite"]["label"], "Elevated")

    def test_rolling_z_absent_when_none(self):
        data = formatter_to_json(self._make_report())
        self.assertNotIn("rolling_z_composite", data)

    def test_credit_spread_and_twexb_in_json(self):
        credit = IndicatorReading("credit_spread", "HY Credit Spread", 4.5,
                                  "2025-04-15", "Elevated", 35)
        twexb = IndicatorReading("twexb", "Trade Weighted USD", 112.0,
                                 "2025-04-15", "Strong", 30)
        report = TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=None, tnx=None, vix=None, dxy=None, approval=None,
            composite_score=0, composite_label="No Data",
            narrative="", nearby_events=[], thresholds={},
            credit_spread=credit, twexb=twexb,
        )
        data = formatter_to_json(report)
        self.assertEqual(data["indicators"]["credit_spread"]["value"], 4.5)
        self.assertEqual(data["indicators"]["twexb"]["value"], 112.0)


# ── Tariffs ─────────────────────────────────────────────────────────────────


class TestLoadTariffs(unittest.TestCase):
    def test_loads_all_tariffs(self):
        tariffs = load_tariffs()
        self.assertGreater(len(tariffs), 0)
        # Each entry should have standard fields
        for t in tariffs:
            self.assertIn("date", t)
            self.assertIn("target", t)
            self.assertIn("status", t)

    def test_filter_by_country(self):
        china = load_tariffs(country="China")
        self.assertGreater(len(china), 0)
        for t in china:
            self.assertIn("china", t["target"].lower())

    def test_filter_by_country_case_insensitive(self):
        result1 = load_tariffs(country="china")
        result2 = load_tariffs(country="CHINA")
        self.assertEqual(len(result1), len(result2))

    def test_filter_by_status(self):
        effective = load_tariffs(status="effective")
        for t in effective:
            self.assertEqual(t["status"], "effective")

    def test_filter_by_country_and_status(self):
        result = load_tariffs(country="China", status="effective")
        for t in result:
            self.assertIn("china", t["target"].lower())
            self.assertEqual(t["status"], "effective")

    def test_nonexistent_country_returns_empty(self):
        result = load_tariffs(country="Narnia")
        self.assertEqual(len(result), 0)

    def test_nonexistent_status_returns_empty(self):
        result = load_tariffs(status="nonexistent_status")
        self.assertEqual(len(result), 0)


class TestGetSummary(unittest.TestCase):
    def test_summary_has_required_keys(self):
        summary = get_summary()
        self.assertIn("total_events", summary)
        self.assertIn("currently_active", summary)
        self.assertIn("paused", summary)
        self.assertIn("removed_or_expired", summary)
        self.assertIn("last_updated", summary)

    def test_total_matches_loaded(self):
        summary = get_summary()
        all_tariffs = load_tariffs()
        self.assertEqual(summary["total_events"], len(all_tariffs))

    def test_categories_sum_reasonable(self):
        summary = get_summary()
        # active + paused + removed should be <= total (some may have other statuses)
        categorized = summary["currently_active"] + summary["paused"] + summary["removed_or_expired"]
        self.assertLessEqual(categorized, summary["total_events"])

    def test_last_updated_is_string(self):
        summary = get_summary()
        self.assertIsNotNone(summary["last_updated"])
        self.assertIsInstance(summary["last_updated"], str)


# ── Historical (get_nearby_events) ──────────────────────────────────────────


class TestGetNearbyEvents(unittest.TestCase):
    def test_no_sp500_returns_last_n(self):
        result = get_nearby_events(sp500=None, limit=3)
        self.assertEqual(len(result), 3)
        # Should be the last 3 events
        self.assertEqual(result, EVENTS[-3:])

    def test_sp500_returns_closest_matches(self):
        result = get_nearby_events(sp500=5500.0, limit=3)
        self.assertEqual(len(result), 3)
        # The closest event with sp500 near 5500 should be first
        sp500_events = [ev for ev in result if ev.sp500 is not None]
        if len(sp500_events) >= 2:
            # First should be closer than second
            dist0 = abs(sp500_events[0].sp500 - 5500.0)
            dist1 = abs(sp500_events[1].sp500 - 5500.0)
            self.assertLessEqual(dist0, dist1)

    def test_limit_respected(self):
        result = get_nearby_events(sp500=5500.0, limit=2)
        self.assertEqual(len(result), 2)

    def test_events_with_none_sp500_sorted_last(self):
        result = get_nearby_events(sp500=5500.0, limit=len(EVENTS))
        # Events with None sp500 get distance 9999, so they should be at the end
        sp500_events = [ev for ev in result if ev.sp500 is not None]
        none_events = [ev for ev in result if ev.sp500 is None]
        # All sp500 events should come before none events in result
        if sp500_events and none_events:
            last_sp500_idx = max(result.index(ev) for ev in sp500_events)
            first_none_idx = min(result.index(ev) for ev in none_events)
            self.assertLess(last_sp500_idx, first_none_idx)


# ── Thresholds (additional coverage) ────────────────────────────────────────


class TestThresholdsExtra(unittest.TestCase):
    """Additional threshold tests for credit_spread and twexb."""

    def test_credit_spread_calm(self):
        zone, score = classify("credit_spread", 2.0)
        self.assertEqual(zone, "Calm")
        self.assertEqual(score, 0)

    def test_credit_spread_stressed(self):
        zone, score = classify("credit_spread", 5.5)
        self.assertEqual(zone, "Stressed")
        self.assertEqual(score, 60)

    def test_credit_spread_panic(self):
        zone, score = classify("credit_spread", 9.0)
        self.assertEqual(zone, "Credit Panic")
        self.assertEqual(score, 100)

    def test_twexb_weak(self):
        zone, score = classify("twexb", 100.0)
        self.assertEqual(zone, "Weak Dollar")
        self.assertEqual(score, 0)

    def test_twexb_strong(self):
        zone, score = classify("twexb", 112.0)
        self.assertEqual(zone, "Strong")
        self.assertEqual(score, 30)

    def test_twexb_crisis(self):
        zone, score = classify("twexb", 130.0)
        self.assertEqual(zone, "Dollar Crisis")
        self.assertEqual(score, 100)

    def test_value_at_exact_boundary(self):
        """Value exactly at lower bound should match that zone."""
        zone, score = classify("vix", 15.0)
        self.assertEqual(zone, "Normal")

    def test_value_above_all_zones_returns_last(self):
        """Value beyond all zones should return the last zone."""
        zone, score = classify("vix", 999.0)
        self.assertEqual(zone, "Panic (2020/2008 level)")
        self.assertEqual(score, 100)

    def test_get_all_thresholds_includes_new_indicators(self):
        result = get_all_thresholds()
        self.assertIn("credit_spread", result)
        self.assertIn("twexb", result)


# ── Discord Alert ───────────────────────────────────────────────────────────


class TestShouldAlert(unittest.TestCase):
    def test_low_score_no_alert(self):
        self.assertFalse(should_alert(30))

    def test_high_score_first_time_alerts(self):
        # Reset cooldown by patching
        with patch("domain.trump_put.discord_alert._last_alert_time", 0):
            self.assertTrue(should_alert(50))

    def test_high_score_but_prev_already_high(self):
        self.assertFalse(should_alert(60, prev_score=50))

    def test_high_score_prev_was_low_alerts(self):
        with patch("domain.trump_put.discord_alert._last_alert_time", 0):
            self.assertTrue(should_alert(50, prev_score=30))

    def test_cooldown_prevents_alert(self):
        with patch("domain.trump_put.discord_alert._last_alert_time", time.time()):
            self.assertFalse(should_alert(50, prev_score=30))


# ── AI Narrative (mocked) ──────────────────────────────────────────────────


class TestAiNarrative(unittest.TestCase):
    """Tests for ai_narrative.generate with mocked OpenAI."""

    def _make_report(self, score: int = 50) -> TrumpPutReport:
        sp500 = IndicatorReading("sp500", "S&P 500", 5500.0, "2025-04-15",
                                 "Media Pressure Zone", 20)
        return TrumpPutReport(
            timestamp=datetime(2025, 4, 15, 12, 0, tzinfo=timezone(timedelta(hours=8))),
            sp500=sp500, tnx=None, vix=None, dxy=None, approval=None,
            composite_score=score,
            composite_label="Elevated",
            narrative="",
            nearby_events=[],
            thresholds={},
        )

    def test_no_api_key_returns_none(self):
        from domain.trump_put import ai_narrative
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            # Clear cache to avoid hitting it
            with ai_narrative._lock:
                ai_narrative._cache.clear()
            result = ai_narrative.generate(self._make_report())
            self.assertIsNone(result)

    def test_cache_hit_returns_cached(self):
        from domain.trump_put import ai_narrative
        with ai_narrative._lock:
            ai_narrative._cache["50"] = ("Cached narrative", time.time())
        result = ai_narrative.generate(self._make_report(50))
        self.assertEqual(result, "Cached narrative")
        # Clean up
        with ai_narrative._lock:
            ai_narrative._cache.clear()

    def test_stale_cache_not_returned(self):
        from domain.trump_put import ai_narrative
        with ai_narrative._lock:
            ai_narrative._cache["50"] = ("Stale narrative", time.time() - 700)
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            result = ai_narrative.generate(self._make_report(50))
            self.assertIsNone(result)
        with ai_narrative._lock:
            ai_narrative._cache.clear()

    @patch("domain.trump_put.ai_narrative.openai", create=True)
    def test_openai_exception_returns_none(self, mock_openai):
        from domain.trump_put import ai_narrative
        with ai_narrative._lock:
            ai_narrative._cache.clear()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("domain.trump_put.ai_narrative.openai") as mock_mod:
                mock_mod.OpenAI.return_value.chat.completions.create.side_effect = Exception("API error")
                result = ai_narrative.generate(self._make_report(99))
                self.assertIsNone(result)
        with ai_narrative._lock:
            ai_narrative._cache.clear()


# ── Approval (mocked) ──────────────────────────────────────────────────────


class TestApproval(unittest.TestCase):
    """Tests for approval.fetch with mocked HTTP."""

    def setUp(self):
        from domain.trump_put import approval as _approval
        with _approval._lock:
            _approval._cache.clear()

    @patch("domain.trump_put.approval._try_538", return_value=(42.5, "2025-04-15"))
    @patch("domain.trump_put.approval._try_rcp", return_value=None)
    def test_538_success(self, mock_rcp, mock_538):
        from domain.trump_put.approval import fetch
        result = fetch()
        self.assertIsNotNone(result)
        self.assertEqual(result, (42.5, "2025-04-15"))

    @patch("domain.trump_put.approval._try_538", return_value=None)
    @patch("domain.trump_put.approval._try_rcp", return_value=(43.0, "2025-04-14"))
    def test_fallback_to_rcp(self, mock_rcp, mock_538):
        from domain.trump_put.approval import fetch
        result = fetch()
        self.assertIsNotNone(result)
        self.assertEqual(result, (43.0, "2025-04-14"))

    @patch("domain.trump_put.approval._try_538", return_value=None)
    @patch("domain.trump_put.approval._try_rcp", return_value=None)
    def test_both_fail_returns_none(self, mock_rcp, mock_538):
        from domain.trump_put.approval import fetch
        result = fetch()
        self.assertIsNone(result)

    def test_cache_hit(self):
        from domain.trump_put import approval as _approval
        with _approval._lock:
            _approval._cache["approval"] = (42.0, "2025-04-15", time.time())
        result = _approval.fetch()
        self.assertEqual(result, (42.0, "2025-04-15"))


# ── Service (generate_report, mocked) ──────────────────────────────────────


class TestGenerateReport(unittest.TestCase):
    """Tests for service.generate_report with all external calls mocked."""

    @patch("domain.trump_put.service.discord_alert")
    @patch("domain.trump_put.service.ai_narrative")
    @patch("domain.trump_put.service.backtest")
    @patch("domain.trump_put.service.approval")
    @patch("domain.trump_put.service.fetcher")
    def test_basic_report_generation(
        self, mock_fetcher, mock_approval, mock_backtest,
        mock_ai_narrative, mock_discord,
    ):
        from domain.trump_put.service import generate_report
        from domain.trump_put.backtest import BacktestResult

        mock_fetcher.fetch_all.return_value = {
            "sp500": (5500.0, "2025-04-15"),
            "tnx": (4.35, "2025-04-15"),
            "vix": (25.0, "2025-04-15"),
            "dxy": (103.0, "2025-04-15"),
        }
        mock_fetcher.fetch_credit_and_usd.return_value = {}
        mock_fetcher.fetch_history.return_value = []
        mock_approval.fetch.return_value = (42.0, "2025-04-15")
        mock_backtest.compute_backtest.return_value = BacktestResult(
            pairs=[], avg_days_to_reversal=0, hit_rates={}, current_prediction=None,
        )
        mock_backtest.to_json.return_value = {"pairs": [], "avg_days_to_reversal": 0}
        mock_ai_narrative.generate.return_value = "AI narrative text."
        mock_discord.should_alert.return_value = False

        report = generate_report()

        self.assertIsNotNone(report)
        self.assertIsNotNone(report.sp500)
        self.assertEqual(report.sp500.value, 5500.0)
        self.assertIsNotNone(report.tnx)
        self.assertIsNotNone(report.approval)
        self.assertEqual(report.narrative, "AI narrative text.")

    @patch("domain.trump_put.service.discord_alert")
    @patch("domain.trump_put.service.ai_narrative")
    @patch("domain.trump_put.service.backtest")
    @patch("domain.trump_put.service.approval")
    @patch("domain.trump_put.service.fetcher")
    def test_report_with_no_data(
        self, mock_fetcher, mock_approval, mock_backtest,
        mock_ai_narrative, mock_discord,
    ):
        from domain.trump_put.service import generate_report
        from domain.trump_put.backtest import BacktestResult

        mock_fetcher.fetch_all.return_value = {}
        mock_fetcher.fetch_credit_and_usd.return_value = {}
        mock_fetcher.fetch_history.return_value = []
        mock_approval.fetch.return_value = None
        mock_backtest.compute_backtest.return_value = BacktestResult(
            pairs=[], avg_days_to_reversal=0, hit_rates={}, current_prediction=None,
        )
        mock_backtest.to_json.return_value = {"pairs": []}
        mock_ai_narrative.generate.return_value = None
        mock_discord.should_alert.return_value = False

        report = generate_report()

        self.assertIsNotNone(report)
        self.assertIsNone(report.sp500)
        self.assertIsNone(report.approval)
        self.assertEqual(report.composite_score, 0)
        self.assertEqual(report.composite_label, "No Data")

    @patch("domain.trump_put.service.discord_alert")
    @patch("domain.trump_put.service.ai_narrative")
    @patch("domain.trump_put.service.backtest")
    @patch("domain.trump_put.service.approval")
    @patch("domain.trump_put.service.fetcher")
    def test_discord_alert_triggered_on_high_score(
        self, mock_fetcher, mock_approval, mock_backtest,
        mock_ai_narrative, mock_discord,
    ):
        from domain.trump_put import service
        from domain.trump_put.backtest import BacktestResult

        # Reset prev_score
        service._prev_score = None

        mock_fetcher.fetch_all.return_value = {
            "sp500": (4900.0, "2025-04-15"),
            "tnx": (4.8, "2025-04-15"),
            "vix": (45.0, "2025-04-15"),
            "dxy": (108.0, "2025-04-15"),
        }
        mock_fetcher.fetch_credit_and_usd.return_value = {}
        mock_fetcher.fetch_history.return_value = []
        mock_approval.fetch.return_value = (32.0, "2025-04-15")
        mock_backtest.compute_backtest.return_value = BacktestResult(
            pairs=[], avg_days_to_reversal=0, hit_rates={}, current_prediction=None,
        )
        mock_backtest.to_json.return_value = {}
        mock_ai_narrative.generate.return_value = "Crisis narrative."
        mock_discord.should_alert.return_value = True

        report = service.generate_report()

        mock_discord.send_alert_async.assert_called_once_with(report)

    @patch("domain.trump_put.service.discord_alert")
    @patch("domain.trump_put.service.ai_narrative")
    @patch("domain.trump_put.service.backtest")
    @patch("domain.trump_put.service.approval")
    @patch("domain.trump_put.service.fetcher")
    def test_report_with_credit_and_twexb(
        self, mock_fetcher, mock_approval, mock_backtest,
        mock_ai_narrative, mock_discord,
    ):
        from domain.trump_put.service import generate_report
        from domain.trump_put.backtest import BacktestResult

        mock_fetcher.fetch_all.return_value = {
            "sp500": (5500.0, "2025-04-15"),
        }
        mock_fetcher.fetch_credit_and_usd.return_value = {
            "credit_spread": (4.5, "2025-04-15"),
            "twexb": (112.0, "2025-04-15"),
        }
        mock_fetcher.fetch_history.return_value = []
        mock_approval.fetch.return_value = None
        mock_backtest.compute_backtest.return_value = BacktestResult(
            pairs=[], avg_days_to_reversal=0, hit_rates={}, current_prediction=None,
        )
        mock_backtest.to_json.return_value = {}
        mock_ai_narrative.generate.return_value = None
        mock_discord.should_alert.return_value = False

        report = generate_report()

        self.assertIsNotNone(report.credit_spread)
        self.assertEqual(report.credit_spread.value, 4.5)
        self.assertIsNotNone(report.twexb)
        self.assertEqual(report.twexb.value, 112.0)

    @patch("domain.trump_put.service.discord_alert")
    @patch("domain.trump_put.service.ai_narrative")
    @patch("domain.trump_put.service.backtest")
    @patch("domain.trump_put.service.approval")
    @patch("domain.trump_put.service.fetcher")
    def test_fallback_narrative_when_ai_returns_none(
        self, mock_fetcher, mock_approval, mock_backtest,
        mock_ai_narrative, mock_discord,
    ):
        from domain.trump_put.service import generate_report
        from domain.trump_put.backtest import BacktestResult

        mock_fetcher.fetch_all.return_value = {
            "sp500": (5500.0, "2025-04-15"),
        }
        mock_fetcher.fetch_credit_and_usd.return_value = {}
        mock_fetcher.fetch_history.return_value = []
        mock_approval.fetch.return_value = None
        mock_backtest.compute_backtest.return_value = BacktestResult(
            pairs=[], avg_days_to_reversal=0, hit_rates={}, current_prediction=None,
        )
        mock_backtest.to_json.return_value = {}
        mock_ai_narrative.generate.return_value = None
        mock_discord.should_alert.return_value = False

        report = generate_report()

        # Should fall back to scoring.generate_narrative
        self.assertIn("S&P 500", report.narrative)


# ── Thresholds _env_float ───────────────────────────────────────────────────


class TestEnvFloat(unittest.TestCase):
    """Tests for _env_float in thresholds.py."""

    def test_env_float_with_valid_value(self):
        from domain.trump_put.thresholds import _env_float
        with patch.dict("os.environ", {"TEST_VAR": "42.5"}):
            self.assertEqual(_env_float("TEST_VAR", 10.0), 42.5)

    def test_env_float_with_empty_value(self):
        from domain.trump_put.thresholds import _env_float
        with patch.dict("os.environ", {"TEST_VAR": ""}):
            self.assertEqual(_env_float("TEST_VAR", 10.0), 10.0)

    def test_env_float_with_missing_var(self):
        from domain.trump_put.thresholds import _env_float
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_env_float("NONEXISTENT_VAR", 99.9), 99.9)

    def test_env_float_with_invalid_value(self):
        from domain.trump_put.thresholds import _env_float
        with patch.dict("os.environ", {"TEST_VAR": "not_a_number"}):
            self.assertEqual(_env_float("TEST_VAR", 10.0), 10.0)


if __name__ == "__main__":
    unittest.main()
