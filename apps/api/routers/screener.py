"""Stock screener endpoint.

Filters Universe companies by:
- sector / exchange / country
- Recent institutional net-buy trend (from chip data in DB if available)
- Monthly revenue YoY growth (from monthly_revenue table if available)
- Whether symbol is in current open positions
- Whether symbol is in any watchlist
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ..config import DB_PATH
from ledger import StockLedger

router = APIRouter()


def _get_open_positions(ledger: StockLedger) -> set[str]:
    try:
        return set(ledger.positions())
    except Exception:
        return set()


def _get_watchlist_symbols(db_path: str) -> set[str]:
    try:
        with sqlite3.connect(db_path) as con:
            rows = con.execute(
                "SELECT DISTINCT symbol FROM watchlist_items WHERE status != 'archived'"
            ).fetchall()
            return {r[0] for r in rows}
    except Exception:
        return set()


def _get_revenue_latest(db_path: str) -> dict[str, dict]:
    """Return {symbol: {latest_yoy_pct, latest_revenue}} from monthly_revenue."""
    result: dict[str, dict] = {}
    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("""
                SELECT symbol, year_month, revenue, yoy_pct
                FROM monthly_revenue
                WHERE (symbol, year_month) IN (
                    SELECT symbol, MAX(year_month) FROM monthly_revenue GROUP BY symbol
                )
            """).fetchall()
            for r in rows:
                result[r["symbol"]] = {
                    "latestYearMonth": r["year_month"],
                    "latestRevenue": r["revenue"],
                    "latestYoyPct": r["yoy_pct"],
                }
    except Exception:
        pass
    return result


def _get_chip_recent(db_path: str, days: int = 10) -> dict[str, dict]:
    """Return recent institutional net trend per symbol from chip_data if exists."""
    result: dict[str, dict] = {}
    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("""
                SELECT symbol,
                    SUM(foreign_net) as foreign_net_sum,
                    SUM(investment_trust_net) as trust_net_sum,
                    COUNT(*) as days
                FROM chip_data
                WHERE date >= date('now', ?)
                GROUP BY symbol
            """, (f"-{days} days",)).fetchall()
            for r in rows:
                result[r["symbol"]] = {
                    "foreignNetSum": r["foreign_net_sum"],
                    "trustNetSum": r["trust_net_sum"],
                    "chipDays": r["days"],
                }
    except Exception:
        pass
    return result


@router.get("/screener", summary="Screen Universe companies")
def screen(
    sector: Optional[str] = Query(None, description="Filter by sector (partial match)"),
    exchange: Optional[str] = Query(None, description="Filter by exchange (partial match)"),
    country: Optional[str] = Query(None, description="Filter by country code e.g. TW, US"),
    in_positions: Optional[bool] = Query(None, description="true = only holdings, false = exclude holdings"),
    in_watchlist: Optional[bool] = Query(None, description="true = only in watchlist"),
    min_yoy_pct: Optional[float] = Query(None, description="Min revenue YoY % (requires revenue data)"),
    foreign_net_positive: Optional[bool] = Query(None, description="true = foreign net buying in recent 10 days"),
    limit: int = Query(50, ge=1, le=200),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Screen companies from Universe with optional filters.
    Enriches each result with revenue trend and chip data if available.
    """
    open_pos = _get_open_positions(ledger)
    watchlist_syms = _get_watchlist_symbols(DB_PATH)
    rev_data = _get_revenue_latest(DB_PATH)
    chip_data = _get_chip_recent(DB_PATH)

    try:
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            companies = con.execute(
                "SELECT symbol, name, exchange, sector, industry, country, currency FROM company_master"
            ).fetchall()
    except Exception:
        companies = []

    results = []
    for co in companies:
        sym = co["symbol"]

        # Apply filters
        if sector and sector.lower() not in (co["sector"] or "").lower():
            continue
        if exchange and exchange.lower() not in (co["exchange"] or "").lower():
            continue
        if country and country.upper() != (co["country"] or "").upper():
            continue
        if in_positions is True and sym not in open_pos:
            continue
        if in_positions is False and sym in open_pos:
            continue
        if in_watchlist is True and sym not in watchlist_syms:
            continue

        rev = rev_data.get(sym)
        if min_yoy_pct is not None:
            if rev is None or rev.get("latestYoyPct") is None:
                continue
            if rev["latestYoyPct"] < min_yoy_pct:
                continue

        chip = chip_data.get(sym)
        if foreign_net_positive is True:
            if chip is None or (chip.get("foreignNetSum") or 0) <= 0:
                continue

        results.append({
            "symbol": sym,
            "name": co["name"],
            "exchange": co["exchange"],
            "sector": co["sector"],
            "industry": co["industry"],
            "country": co["country"],
            "inPositions": sym in open_pos,
            "inWatchlist": sym in watchlist_syms,
            "revenue": rev,
            "chip": chip,
        })

    return {
        "total": len(results),
        "results": results[:limit],
    }
