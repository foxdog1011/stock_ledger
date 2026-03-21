"""Asset allocation / portfolio composition endpoint.

Breaks down the portfolio by:
- Asset class (equity vs cash)
- Sector (from company_master table)
- Geography (Taiwan / US / Other from exchange field in universe)
- Individual position weights
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ..config import DB_PATH
from ledger import StockLedger

router = APIRouter()


def _get_universe_meta(db_path: str) -> dict[str, dict]:
    """Return {symbol: {sector, exchange, country}} from company_master / universe."""
    meta: dict[str, dict] = {}
    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            # company_master (used by rolling/sector check)
            rows = con.execute(
                "SELECT symbol, sector FROM company_master"
            ).fetchall()
            for r in rows:
                sym = r["symbol"]
                if sym not in meta:
                    meta[sym] = {}
                meta[sym]["sector"] = r["sector"]
    except Exception:
        pass

    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT symbol, sector, exchange, country FROM company_master"
            ).fetchall()
            for r in rows:
                sym = r["symbol"]
                if sym not in meta:
                    meta[sym] = {}
                if r["sector"]:
                    meta[sym]["sector"] = r["sector"]
                meta[sym]["exchange"] = r["exchange"]
                meta[sym]["country"] = r["country"]
    except Exception:
        pass

    return meta


def _classify_geography(exchange: Optional[str], country: Optional[str], symbol: str) -> str:
    """Classify a symbol into a geographic bucket."""
    if country:
        c = country.upper()
        if c in ("TW", "TWN", "TAIWAN"):
            return "Taiwan"
        if c in ("US", "USA", "UNITED STATES"):
            return "US"
    if exchange:
        ex = exchange.upper()
        if any(x in ex for x in ("TWSE", "TPEx", "OTC", "TSE", "TW")):
            return "Taiwan"
        if any(x in ex for x in ("NYSE", "NASDAQ", "AMEX", "US")):
            return "US"
        if "HK" in ex or "HKEX" in ex:
            return "HK"
    # Heuristic: pure numeric 4-digit = Taiwan
    if symbol.isdigit() and len(symbol) == 4:
        return "Taiwan"
    return "Other"


@router.get("/allocation", summary="Portfolio asset allocation breakdown")
def get_allocation(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Returns a multi-dimensional breakdown of portfolio allocation:
    - byAssetClass: equity vs cash
    - bySector: market value per sector
    - byGeography: Taiwan / US / Other
    - positions: individual weights
    """
    snap = ledger.equity_snapshot(as_of=as_of)
    positions = snap.get("positions", {})
    cash = snap.get("cash", 0.0)
    total_mv = sum((p.get("market_value") or 0) for p in positions.values())
    total_equity = cash + total_mv

    meta = _get_universe_meta(DB_PATH)

    # ── By Asset Class ──
    by_asset = [
        {"label": "Equity", "value": round(total_mv, 2),
         "pct": round(total_mv / total_equity * 100, 1) if total_equity > 0 else 0},
        {"label": "Cash",   "value": round(cash, 2),
         "pct": round(cash / total_equity * 100, 1) if total_equity > 0 else 0},
    ]

    # ── By Sector ──
    sector_map: dict[str, float] = {}
    for sym, pos in positions.items():
        mv = pos.get("market_value") or 0
        sector = (meta.get(sym) or {}).get("sector") or "未分類"
        sector_map[sector] = sector_map.get(sector, 0.0) + mv

    by_sector = sorted([
        {
            "label": sec,
            "value": round(mv, 2),
            "pct": round(mv / total_equity * 100, 1) if total_equity > 0 else 0,
            "symbols": [s for s, p in positions.items()
                        if ((meta.get(s) or {}).get("sector") or "未分類") == sec],
        }
        for sec, mv in sector_map.items()
    ], key=lambda x: -x["value"])

    # ── By Geography ──
    geo_map: dict[str, float] = {}
    for sym, pos in positions.items():
        mv = pos.get("market_value") or 0
        m = meta.get(sym) or {}
        geo = _classify_geography(m.get("exchange"), m.get("country"), sym)
        geo_map[geo] = geo_map.get(geo, 0.0) + mv

    by_geography = sorted([
        {
            "label": geo,
            "value": round(mv, 2),
            "pct": round(mv / total_equity * 100, 1) if total_equity > 0 else 0,
        }
        for geo, mv in geo_map.items()
    ], key=lambda x: -x["value"])

    # ── Individual positions ──
    pos_list = sorted([
        {
            "symbol": sym,
            "marketValue": round((p.get("market_value") or 0), 2),
            "pct": round((p.get("market_value") or 0) / total_equity * 100, 1) if total_equity > 0 else 0,
            "sector": (meta.get(sym) or {}).get("sector") or "未分類",
            "geography": _classify_geography(
                (meta.get(sym) or {}).get("exchange"),
                (meta.get(sym) or {}).get("country"),
                sym,
            ),
        }
        for sym, p in positions.items()
        if (p.get("market_value") or 0) > 0
    ], key=lambda x: -x["marketValue"])

    return {
        "asOf": snap.get("date", as_of),
        "totalEquity": round(total_equity, 2),
        "totalMarketValue": round(total_mv, 2),
        "cash": round(cash, 2),
        "byAssetClass": by_asset,
        "bySector": by_sector,
        "byGeography": by_geography,
        "positions": pos_list,
    }
