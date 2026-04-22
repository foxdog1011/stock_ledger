"""Yahoo Finance price provider (no API key required).

Uses the public Yahoo Finance chart API to fetch recent closing prices.
Works for US, HK, and other exchange symbols.

API:
  https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
    ?interval=1d&range=5d
"""
from __future__ import annotations

import datetime
import json
import urllib.request
from typing import Optional

from .base import PriceProvider, PriceRecord

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json",
}


class YahooProvider(PriceProvider):
    name = "yahoo"

    def get_latest_close(self, symbol: str, as_of: str) -> Optional[PriceRecord]:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            "?interval=1d&range=10d"
        )
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            raise ValueError(f"Yahoo Finance request failed for {symbol}: {exc}") from exc

        try:
            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
        except (KeyError, IndexError, TypeError):
            return None

        if not timestamps or not closes:
            return None

        # Filter to on or before as_of; find the latest
        best_date: Optional[str] = None
        best_close: Optional[float] = None

        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            dt = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            if dt <= as_of:
                if best_date is None or dt > best_date:
                    best_date = dt
                    best_close = float(close)

        if best_date is None or best_close is None:
            return None

        return PriceRecord(symbol=symbol, date=best_date, close=best_close)

    # get_bulk_close inherited from PriceProvider (per-symbol loop)
