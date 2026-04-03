"""Taiwan margin trading (融資融券) data via FinMind API."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta

_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch_margin_trading(symbol: str, days: int = 30) -> list[dict]:
    """
    Return last `days` calendar days of margin trading data for `symbol`.
    Each dict: {date, margin_balance, margin_buy, margin_sell, short_balance, short_buy, short_sell}
    Returns empty list if FINMIND_TOKEN not set or request fails.
    """
    token = os.getenv("FINMIND_TOKEN", "").strip()
    if not token:
        return []

    end = date.today()
    start = end - timedelta(days=days + 10)  # extra buffer for non-trading days

    params = urllib.parse.urlencode({
        "dataset": "TaiwanStockMarginPurchaseShortSale",
        "data_id": symbol,
        "start_date": str(start),
        "end_date": str(end),
        "token": token,
    })
    url = f"{_FINMIND_URL}?{params}"

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        if data.get("status") != 200 or not data.get("data"):
            return []

        result = []
        for row in data["data"]:
            result.append({
                "date": row.get("date", ""),
                "margin_buy": int(row.get("MarginPurchaseBuy", 0) or 0),
                "margin_sell": int(row.get("MarginPurchaseSell", 0) or 0),
                "margin_balance": int(row.get("MarginPurchaseTodayBalance", 0) or 0),
                "short_buy": int(row.get("ShortSaleBuy", 0) or 0),
                "short_sell": int(row.get("ShortSaleSell", 0) or 0),
                "short_balance": int(row.get("ShortSaleTodayBalance", 0) or 0),
            })

        return sorted(result, key=lambda x: x["date"])[-days:]

    except Exception:
        return []
