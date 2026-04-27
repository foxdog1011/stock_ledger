"""Local API helpers for fetching chip data and company names."""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import date, timedelta

from fastapi import HTTPException

from apps.api.services.video_engine.constants import TICKER_NAME

logger = logging.getLogger(__name__)

_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
_API_KEY = os.environ.get("JARVIS_KEY", "")


def _api_headers() -> dict:
    """Build headers for internal API calls, including API key if set."""
    h = {"Accept": "application/json"}
    if _API_KEY:
        h["X-API-Key"] = _API_KEY
    return h


def get_chip_data(symbol: str, days: int) -> dict:
    """Fetch chip data from the local API for a given symbol and time range."""
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=days + 10)).isoformat()
    url   = f"{_API_BASE}/api/chip/{symbol}/range?start={start}&end={end}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=_api_headers()),
            timeout=20,
        ) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise HTTPException(502, f"Chip data unavailable: {exc}") from exc

    # Trim to last N trading days so numbers match the requested scope
    daily = data.get("daily", [])
    if daily and len(daily) > days:
        data["daily"] = daily[-days:]
    return data


def get_company_name(symbol: str) -> str:
    """Look up company name via research API, fall back to built-in ticker map."""
    url = f"{_API_BASE}/api/research/{symbol}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=_api_headers()),
            timeout=10,
        ) as resp:
            name = json.loads(resp.read()).get("name", "")
            if name and name != symbol:
                return name
    except Exception:
        pass
    return TICKER_NAME.get(symbol, symbol)


def compute_foreign_net_k(summary: dict, daily: list[dict]) -> int:
    """Return total foreign net in 千張 from summary or daily fallback."""
    total = summary.get("foreign_net_total")
    if total is None and daily:
        total = sum(d.get("foreign", {}).get("net", 0) for d in daily)
    return round((total or 0) / 1000)


def get_sector_chip(symbols: list[str], sector_name: str, days: int) -> dict:
    """Fetch chip data for each symbol and aggregate into a sector summary."""
    all_data: list[dict] = []
    failed: list[str] = []

    for sym in symbols:
        try:
            data = get_chip_data(sym, days)
            all_data.append({"symbol": sym, "name": get_company_name(sym), **data})
        except Exception:
            logger.warning("Sector chip fetch failed for %s", sym)
            failed.append(sym)

    if not all_data:
        raise HTTPException(502, f"No chip data available for any symbol in {sector_name}")

    # Build unified daily grid: sum across all symbols per date
    date_map: dict[str, dict] = {}
    for item in all_data:
        for d in item.get("daily", []):
            dt = d["date"]
            if dt not in date_map:
                date_map[dt] = {
                    "date": dt,
                    "foreign":          {"net": 0},
                    "investment_trust": {"net": 0},
                    "dealer":           {"net": 0},
                    "total_net": 0,
                }
            date_map[dt]["foreign"]["net"]          += d.get("foreign", {}).get("net", 0)
            date_map[dt]["investment_trust"]["net"] += d.get("investment_trust", {}).get("net", 0)
            date_map[dt]["dealer"]["net"]           += d.get("dealer", {}).get("net", 0)
            date_map[dt]["total_net"]               += d.get("total_net", 0)

    daily = sorted(date_map.values(), key=lambda x: x["date"])

    summary = {
        "foreign_net_total":          sum(d["foreign"]["net"]          for d in daily),
        "investment_trust_net_total": sum(d["investment_trust"]["net"] for d in daily),
        "dealer_net_total":           sum(d["dealer"]["net"]           for d in daily),
        "total_net":                  sum(d["total_net"]               for d in daily),
    }

    return {
        "sector_name": sector_name,
        "symbols": [{"symbol": s["symbol"], "name": s["name"]} for s in all_data],
        "failed": failed,
        "daily": daily,
        "summary": summary,
    }
