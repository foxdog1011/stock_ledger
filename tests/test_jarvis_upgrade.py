"""Smoke tests for J.A.R.V.I.S. upgrades added 2026-03-30.

Covers:
- get_quote (MCP tool)
- get_technical_indicators (MCP tool)
- get_news (MCP tool)
- chat memory (load/save/limit)

All yfinance calls are mocked so tests run offline and fast.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from unittest.mock import MagicMock, patch


def _tmp_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _make_hist_df(n: int = 200):
    import pandas as pd
    import numpy as np
    dates = pd.bdate_range(end=date.today(), periods=n)
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(len(dates)).cumsum() * 0.5
    return pd.DataFrame({"Close": close, "Volume": [1_000_000] * len(dates)}, index=dates)


# ── get_quote ─────────────────────────────────────────────────────────────────

class TestGetQuote(unittest.TestCase):
    def _make_ticker(self, price=150.0, prev=145.0):
        t = MagicMock()
        t.fast_info = MagicMock(
            last_price=price, previous_close=prev,
            three_month_average_volume=10_000_000, market_cap=2_000_000_000,
            year_high=200.0, year_low=100.0,
        )
        t.info = {"trailingPE": 25.5, "dividendYield": 0.012, "currency": "USD", "exchange": "NMS"}
        return t

    @patch("yfinance.Ticker")
    def test_price_and_change_pct(self, mock_cls):
        mock_cls.return_value = self._make_ticker(150.0, 145.0)
        import os; os.environ.setdefault("DB_PATH", _tmp_db())
        from apps.mcp.server import get_quote
        r = get_quote("AAPL")
        self.assertNotIn("error", r)
        self.assertEqual(r["symbol"], "AAPL")
        self.assertAlmostEqual(r["price"], 150.0)
        expected_pct = round((150.0 - 145.0) / 145.0 * 100, 2)
        self.assertAlmostEqual(r["change_pct"], expected_pct)

    @patch("yfinance.Ticker")
    def test_taiwan_symbol_gets_tw_suffix(self, mock_cls):
        mock_cls.return_value = self._make_ticker(600.0, 595.0)
        import os; os.environ.setdefault("DB_PATH", _tmp_db())
        from apps.mcp.server import get_quote
        r = get_quote("2330")
        self.assertEqual(r["yf_symbol"], "2330.TW")


# ── get_technical_indicators ──────────────────────────────────────────────────

class TestGetTechnicalIndicators(unittest.TestCase):
    @patch("yfinance.Ticker")
    def test_all_indicator_sections_present(self, mock_cls):
        mock_cls.return_value.history.return_value = _make_hist_df()
        import os; os.environ.setdefault("DB_PATH", _tmp_db())
        from apps.mcp.server import get_technical_indicators
        r = get_technical_indicators("AAPL", days=120)
        self.assertNotIn("error", r)
        for key in ("ma", "rsi14", "rsi_signal", "macd", "bollinger", "latest_close"):
            self.assertIn(key, r, f"Missing key: {key}")
        for ma_key in ("ma5", "ma20"):
            self.assertIn(ma_key, r["ma"])
        for macd_key in ("macd", "signal", "histogram", "trend"):
            self.assertIn(macd_key, r["macd"])
        self.assertIn(r["rsi_signal"], ("overbought", "neutral", "oversold"))
        self.assertIn(r["bollinger"]["position"], ("overbought", "oversold", "normal"))

    @patch("yfinance.Ticker")
    def test_empty_history_returns_error(self, mock_cls):
        import pandas as pd
        mock_cls.return_value.history.return_value = pd.DataFrame()
        import os; os.environ.setdefault("DB_PATH", _tmp_db())
        from apps.mcp.server import get_technical_indicators
        r = get_technical_indicators("BADTICKER")
        self.assertIn("error", r)


# ── get_news ──────────────────────────────────────────────────────────────────

class TestGetNews(unittest.TestCase):
    def _mock_news(self):
        return [
            {"content": {"title": "AAPL hits record", "provider": {"displayName": "Reuters"},
                         "canonicalUrl": {"url": "https://r.com/1"}, "pubDate": "2026-03-30T10:00:00Z"}},
            {"content": {"title": "Apple launches product", "provider": {"displayName": "Bloomberg"},
                         "canonicalUrl": {"url": "https://b.com/1"}, "pubDate": "2026-03-30T09:00:00Z"}},
        ]

    @patch("yfinance.Ticker")
    def test_articles_parsed_correctly(self, mock_cls):
        mock_cls.return_value.news = self._mock_news()
        import os; os.environ.setdefault("DB_PATH", _tmp_db())
        from apps.mcp.server import get_news
        r = get_news("AAPL", count=2)
        self.assertNotIn("error", r)
        self.assertEqual(r["count"], 2)
        self.assertEqual(r["articles"][0]["title"], "AAPL hits record")
        self.assertEqual(r["articles"][0]["publisher"], "Reuters")

    @patch("yfinance.Ticker")
    def test_empty_news_ok(self, mock_cls):
        mock_cls.return_value.news = []
        import os; os.environ.setdefault("DB_PATH", _tmp_db())
        from apps.mcp.server import get_news
        r = get_news("UNKNOWN")
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["articles"], [])


# ── chat memory ───────────────────────────────────────────────────────────────

class TestChatMemory(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        import apps.api.routers.chat as m
        m.DB_PATH = self.db
        self.mod = m

    def test_save_and_load_roundtrip(self):
        sid = "session-abc"
        msgs = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
        self.mod._save_messages(sid, msgs)
        loaded = self.mod._load_memory(sid)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["content"], "Hi")
        self.assertEqual(loaded[1]["role"], "assistant")

    def test_empty_session_returns_empty_list(self):
        result = self.mod._load_memory("no-such-session")
        self.assertEqual(result, [])

    def test_respects_context_limit(self):
        sid = "big-session"
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
        self.mod._save_messages(sid, msgs)
        loaded = self.mod._load_memory(sid)
        self.assertLessEqual(len(loaded), self.mod._MEMORY_CONTEXT_LIMIT)

    def test_chronological_order(self):
        sid = "order-test"
        msgs = [{"role": "user", "content": f"turn {i}"} for i in range(5)]
        self.mod._save_messages(sid, msgs)
        loaded = self.mod._load_memory(sid)
        for i, m in enumerate(loaded):
            self.assertEqual(m["content"], f"turn {i}")


if __name__ == "__main__":
    unittest.main()
