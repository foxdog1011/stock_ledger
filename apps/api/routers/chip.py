"""三大法人籌碼 endpoints — institutional investor buy/sell data.

Uses TWSE public API (no token required) for listed stocks.
Falls back to FinMind API if FINMIND_TOKEN is set, which covers OTC stocks too.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _fetch_twse_chip(symbol: str, date_str: str) -> Optional[dict]:
    """Fetch institutional data from TWSE public API."""
    params = urllib.parse.urlencode({
        "date": date_str.replace("-", ""),
        "selectType": "ALLBUT0999",
        "response": "json",
    })
    url = f"{_TWSE_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        if data.get("stat") != "OK" or not data.get("data"):
            return None

        for row in data["data"]:
            if row[0].strip() == symbol:
                # row format: [symbol, name, 外資買, 外資賣, 外資淨, 投信買, 投信賣, 投信淨, 自營商買, 自營商賣, 自營商淨, 三大合計]
                def parse_int(s: str) -> int:
                    return int(s.replace(",", "").strip() or "0")

                return {
                    "symbol": symbol,
                    "date": date_str,
                    "source": "TWSE",
                    "foreign": {
                        "buy": parse_int(row[2]),
                        "sell": parse_int(row[3]),
                        "net": parse_int(row[4]),
                    },
                    "investment_trust": {
                        "buy": parse_int(row[5]),
                        "sell": parse_int(row[6]),
                        "net": parse_int(row[7]),
                    },
                    "dealer": {
                        "buy": parse_int(row[8]),
                        "sell": parse_int(row[9]),
                        "net": parse_int(row[10]),
                    },
                    "total_net": parse_int(row[11]),
                }
        return None
    except Exception:
        return None


def _fetch_finmind_chip(symbol: str, date_str: str) -> Optional[dict]:
    """Fetch institutional data from FinMind API (requires FINMIND_TOKEN)."""
    token = os.getenv("FINMIND_TOKEN", "").strip()
    if not token:
        return None

    params = urllib.parse.urlencode({
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": symbol,
        "start_date": date_str,
        "end_date": date_str,
        "token": token,
    })
    url = f"{_FINMIND_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        if data.get("status") != 200 or not data.get("data"):
            return None

        result: dict = {
            "symbol": symbol,
            "date": date_str,
            "source": "FinMind",
            "foreign": {"buy": 0, "sell": 0, "net": 0},
            "investment_trust": {"buy": 0, "sell": 0, "net": 0},
            "dealer": {"buy": 0, "sell": 0, "net": 0},
            "total_net": 0,
        }

        name_map = {
            "外資": "foreign",
            "外資及陸資": "foreign",
            "投信": "investment_trust",
            "自營商": "dealer",
        }

        for row in data["data"]:
            key = name_map.get(row.get("name", ""))
            if key:
                buy = int(row.get("buy", 0) or 0)
                sell = int(row.get("sell", 0) or 0)
                result[key] = {"buy": buy, "sell": sell, "net": buy - sell}

        result["total_net"] = (
            result["foreign"]["net"]
            + result["investment_trust"]["net"]
            + result["dealer"]["net"]
        )
        return result
    except Exception:
        return None


def _fetch_chip_range(symbol: str, start: str, end: str) -> list[dict]:
    """Fetch chip data for a date range. Tries FinMind first (covers OTC), falls back to TWSE."""
    import datetime
    results = []
    current = datetime.date.fromisoformat(start)
    end_date = datetime.date.fromisoformat(end)

    while current <= end_date:
        if current.weekday() < 5:  # weekdays only
            date_str = current.isoformat()
            row = _fetch_finmind_chip(symbol, date_str) or _fetch_twse_chip(symbol, date_str)
            if row:
                results.append(row)
        current += datetime.timedelta(days=1)

    return results


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/chip/{symbol}", summary="三大法人買賣超 for a single date")
def get_chip(
    symbol: str,
    date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
):
    """
    Return institutional investor (三大法人) buy/sell data for a Taiwan stock.

    - **外資** (Foreign investors)
    - **投信** (Investment trust / domestic funds)
    - **自營商** (Dealers / proprietary trading)

    Data source: TWSE public API (listed stocks). OTC stocks require FinMind token.
    """
    date_str = date or str(Date.today())

    # Try FinMind first if token available, then TWSE
    result = _fetch_finmind_chip(symbol, date_str) or _fetch_twse_chip(symbol, date_str)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No chip data found for {symbol} on {date_str}. "
                   "OTC stocks may require FINMIND_TOKEN env var.",
        )
    return result


@router.get("/chip/{symbol}/range", summary="三大法人買賣超 for a date range")
def get_chip_range(
    symbol: str,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
):
    """
    Return institutional buy/sell data for a date range (TWSE listed stocks only).
    Skips weekends and dates with no data. Max 30 days to avoid rate limiting.
    """
    import datetime
    start_dt = datetime.date.fromisoformat(start)
    end_dt = datetime.date.fromisoformat(end)
    if (end_dt - start_dt).days > 30:
        raise HTTPException(status_code=400, detail="Max range is 30 days.")

    rows = _fetch_chip_range(symbol, start, end)

    total_net = sum(r["total_net"] for r in rows)
    foreign_net = sum(r["foreign"]["net"] for r in rows)
    trust_net = sum(r["investment_trust"]["net"] for r in rows)
    dealer_net = sum(r["dealer"]["net"] for r in rows)

    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "days_with_data": len(rows),
        "summary": {
            "foreign_net_total": foreign_net,
            "investment_trust_net_total": trust_net,
            "dealer_net_total": dealer_net,
            "total_net": total_net,
        },
        "daily": rows,
    }


@router.get("/chip/portfolio/summary", summary="三大法人買賣超 for all holdings")
def get_portfolio_chip(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    ledger=None,
):
    """Fetch chip data for all current holdings in one call."""
    from ..deps import get_ledger
    import fastapi
    date_str = date or str(Date.today())
    ledger = get_ledger()
    snap = ledger.equity_snapshot(as_of=date_str)
    symbols = list(snap.get("positions", {}).keys())

    results = []
    for sym in symbols:
        row = _fetch_finmind_chip(sym, date_str) or _fetch_twse_chip(sym, date_str)
        if row:
            results.append(row)
        else:
            results.append({
                "symbol": sym,
                "date": date_str,
                "source": None,
                "error": "no data",
            })

    return {"date": date_str, "holdings": results}
