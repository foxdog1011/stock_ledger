"""TWSE (Taiwan Stock Exchange) price provider.

Fetches all-stock closing prices from the public TWSE REST API.
Falls back up to 10 calendar days on non-trading days.

TWSE endpoint:
  https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json&date=YYYYMMDD
Fields returned: ["證券代號", "證券名稱", "成交股數", ..., "收盤價" (index 8), ...]

TPEX (OTC) endpoint (for stocks NOT on TWSE main board):
  https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php
    ?l=zh-tw&d=YYYY/MM/DD&se=EW
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
}


class TWSeProvider(PriceProvider):
    name = "twse"

    # ── TWSE main board ──────────────────────────────────────────────────────

    def _fetch_twse_day(self, date_str: str) -> dict[str, float]:
        """Return {symbol: close} for all TWSE-listed stocks on *date_str*."""
        date_nodash = date_str.replace("-", "")
        url = (
            f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL"
            f"?response=json&date={date_nodash}"
        )
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception:
            return {}

        if data.get("stat") != "OK":
            return {}

        fields = data.get("fields", [])
        rows = data.get("data", [])
        if not rows:
            return {}

        try:
            sym_idx = fields.index("證券代號")
            close_idx = fields.index("收盤價")
        except ValueError:
            sym_idx, close_idx = 0, 8

        result: dict[str, float] = {}
        for row in rows:
            try:
                symbol = str(row[sym_idx]).strip()
                close_str = str(row[close_idx]).replace(",", "").strip()
                if close_str and close_str not in ("--", ""):
                    result[symbol] = float(close_str)
            except (ValueError, IndexError):
                continue
        return result

    # ── TPEX (OTC) board ─────────────────────────────────────────────────────

    def _fetch_tpex_day(self, date_str: str) -> dict[str, float]:
        """Return {symbol: close} for all TPEX-listed stocks on *date_str*."""
        d = datetime.date.fromisoformat(date_str)
        # TPEX uses YYYY/MM/DD format
        date_slash = d.strftime("%Y/%m/%d")
        url = (
            "https://www.tpex.org.tw/web/stock/aftertrading/"
            "otc_quotes_no1430/stk_wn1430_result.php"
            f"?l=zh-tw&d={date_slash}&se=EW"
        )
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception:
            return {}

        rows = data.get("aaData", [])
        if not rows:
            return {}

        # TPEX aaData: [code, name, close, ...]  (index 0=code, 2=close)
        result: dict[str, float] = {}
        for row in rows:
            try:
                symbol = str(row[0]).strip()
                close_str = str(row[2]).replace(",", "").strip()
                if close_str and close_str not in ("--", ""):
                    result[symbol] = float(close_str)
            except (ValueError, IndexError):
                continue
        return result

    # ── Public interface ─────────────────────────────────────────────────────

    def get_bulk_close(
        self, symbols: list[str], as_of: str
    ) -> dict[str, PriceRecord]:
        """Fetch closing prices for *symbols* in bulk.

        Tries up to 10 calendar days before *as_of* to find a trading day.
        Checks TWSE then TPEX for each day.
        """
        date = datetime.date.fromisoformat(as_of)
        result: dict[str, PriceRecord] = {}
        remaining = set(symbols)

        for i in range(10):
            if not remaining:
                break
            target = date - datetime.timedelta(days=i)
            target_str = target.isoformat()

            twse_prices = self._fetch_twse_day(target_str)
            tpex_prices = self._fetch_tpex_day(target_str)
            all_prices = {**twse_prices, **tpex_prices}

            found = set()
            for sym in list(remaining):
                if sym in all_prices:
                    result[sym] = PriceRecord(
                        symbol=sym, date=target_str, close=all_prices[sym]
                    )
                    found.add(sym)
            remaining -= found

        return result

    def get_latest_close(self, symbol: str, as_of: str) -> Optional[PriceRecord]:
        bulk = self.get_bulk_close([symbol], as_of)
        return bulk.get(symbol)
