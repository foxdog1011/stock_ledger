from __future__ import annotations

import json as _json
import logging
import os
import threading
import time
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SYMBOLS = {
    "sp500": "^GSPC",
    "tnx":   "^TNX",
    "vix":   "^VIX",
    "dxy":   "DX-Y.NYB",
}

_POLYGON_TICKERS = {
    "sp500": "I:SPX",
    "vix":   "I:VIX",
}

_FRED_SERIES = {
    "sp500": "SP500",
    "tnx":   "DGS10",
    "vix":   "VIXCLS",
}


@dataclass
class _CacheEntry:
    value: float
    as_of: str
    fetched_at: float


def _fetch_polygon_index(indicator: str) -> tuple[float, str] | None:
    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    ticker = _POLYGON_TICKERS.get(indicator)
    if not api_key or not ticker:
        return None
    try:
        url = (
            f"https://api.polygon.io/v2/snapshot/locale/us/markets/indices/tickers/{ticker}"
            f"?apiKey={api_key}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "stock-ledger/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        session = data.get("results", {}).get("session", {})
        value = session.get("close") or session.get("previous_close")
        if value is None:
            return None
        today = time.strftime("%Y-%m-%d")
        return (float(value), today)
    except Exception:
        logger.exception("Polygon fetch failed for %s", ticker)
        return None


def _fetch_polygon_treasury() -> tuple[float, str] | None:
    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        url = (
            f"https://api.polygon.io/v1/fed/treasury-yields"
            f"?order=desc&limit=1&apiKey={api_key}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "stock-ledger/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return None
        row = results[0]
        value = row.get("ten_year")
        date = row.get("date", time.strftime("%Y-%m-%d"))
        if value is None:
            return None
        return (float(value), date)
    except Exception:
        logger.exception("Polygon treasury fetch failed")
        return None


def _fetch_polygon(indicator: str) -> tuple[float, str] | None:
    if indicator == "tnx":
        return _fetch_polygon_treasury()
    return _fetch_polygon_index(indicator)


class MarketDataFetcher:
    def __init__(self, cache_ttl: int = 300):
        self._ttl = cache_ttl
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def _check_cache(self, indicator: str) -> tuple[float, str] | None:
        with self._lock:
            cached = self._cache.get(indicator)
            if cached and (time.time() - cached.fetched_at) < self._ttl:
                return (cached.value, cached.as_of)
        return None

    def _store_cache(self, indicator: str, value: float, as_of: str) -> None:
        with self._lock:
            self._cache[indicator] = _CacheEntry(
                value=value, as_of=as_of, fetched_at=time.time()
            )

    def _stale_cache(self, indicator: str) -> tuple[float, str] | None:
        with self._lock:
            stale = self._cache.get(indicator)
            if stale:
                logger.info("Returning stale cache for %s", indicator)
                return (stale.value, stale.as_of)
        return None

    def fetch(self, indicator: str) -> tuple[float, str] | None:
        if indicator not in _SYMBOLS:
            logger.warning("Unknown indicator: %s", indicator)
            return None

        cached = self._check_cache(indicator)
        if cached:
            return cached

        # 1. Polygon.io (near real-time, 15-min delay)
        result = _fetch_polygon(indicator)
        if result:
            self._store_cache(indicator, result[0], result[1])
            return result

        # 2. yfinance (T-1 close)
        try:
            import yfinance as yf
            yahoo_sym = _SYMBOLS[indicator]
            ticker = yf.Ticker(yahoo_sym)
            hist = ticker.history(period="5d")
            if not hist.empty:
                last_row = hist.iloc[-1]
                value = float(last_row["Close"])
                as_of = str(hist.index[-1].date())
                self._store_cache(indicator, value, as_of)
                return (value, as_of)
            logger.warning("No data from yfinance for %s", yahoo_sym)
        except Exception:
            logger.exception("Failed to fetch %s from yfinance", _SYMBOLS[indicator])

        # 3. FRED (daily, limited symbols)
        fred_result = _fetch_fred(indicator)
        if fred_result:
            self._store_cache(indicator, fred_result[0], fred_result[1])
            return fred_result

        # 4. Stale cache
        return self._stale_cache(indicator)

    def fetch_all(self) -> dict[str, tuple[float, str]]:
        results: dict[str, tuple[float, str]] = {}
        for key in _SYMBOLS:
            result = self.fetch(key)
            if result is not None:
                results[key] = result
        return results

    def fetch_history(self, indicator: str, period: str = "6mo") -> list[dict]:
        yahoo_sym = _SYMBOLS.get(indicator)
        if yahoo_sym is None:
            return []
        try:
            import yfinance as yf
            hist = yf.Ticker(yahoo_sym).history(period=period)
            return [
                {"date": str(idx.date()), "close": float(row["Close"])}
                for idx, row in hist.iterrows()
            ]
        except Exception:
            logger.exception("Failed to fetch history for %s", yahoo_sym)
            return []


def _fetch_fred(indicator: str) -> tuple[float, str] | None:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    series = _FRED_SERIES.get(indicator)
    if not api_key or not series:
        return None
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series}&api_key={api_key}&file_type=json"
            f"&limit=5&sort_order=desc"
        )
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = _json.loads(resp.read())
        for obs in data.get("observations", []):
            if obs["value"] != ".":
                return (float(obs["value"]), obs["date"])
        return None
    except Exception:
        logger.exception("FRED fetch failed for %s", series)
        return None


_default_fetcher = MarketDataFetcher()


def fetch(indicator: str) -> tuple[float, str] | None:
    return _default_fetcher.fetch(indicator)


def fetch_all() -> dict[str, tuple[float, str]]:
    return _default_fetcher.fetch_all()


def fetch_history(indicator: str, period: str = "6mo") -> list[dict]:
    return _default_fetcher.fetch_history(indicator, period)
