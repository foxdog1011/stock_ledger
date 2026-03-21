"""Taiwan monthly revenue (月營收) endpoints.

Fetches from FinMind public API (TaiwanStockMonthRevenue dataset).
Works without a token for recent data; uses FINMIND_TOKEN if available for
older history.

Stores results in a local `monthly_revenue` SQLite table.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import DB_PATH

router = APIRouter()

_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _ensure_table() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS monthly_revenue (
                symbol      TEXT NOT NULL,
                year_month  TEXT NOT NULL,   -- YYYY-MM (Gregorian)
                revenue     REAL NOT NULL,
                yoy_pct     REAL,            -- vs same month last year
                mom_pct     REAL,            -- vs previous month
                fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (symbol, year_month)
            )
        """)
        con.commit()


# ── FinMind fetch ──────────────────────────────────────────────────────────────

def _fetch_finmind_revenue(symbol: str, start_date: str = "2023-01-01") -> list[dict]:
    """Fetch monthly revenue from FinMind TaiwanStockMonthRevenue dataset."""
    token = os.getenv("FINMIND_TOKEN", "")
    params: dict = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": symbol,
        "start_date": start_date,
    }
    if token:
        params["token"] = token

    url = f"{_FINMIND_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"FinMind request failed: {exc}") from exc

    if data.get("status") != 200:
        raise ValueError(f"FinMind error: {data.get('msg', 'unknown')}")

    results = []
    for row in data.get("data", []):
        # FinMind date field is the reporting date (YYYY-MM-01)
        # revenue_year / revenue_month = the actual month being reported
        rev_year = row.get("revenue_year")
        rev_month = row.get("revenue_month")
        if not rev_year or not rev_month:
            continue
        year_month = f"{rev_year}-{int(rev_month):02d}"
        revenue = row.get("revenue", 0)
        if revenue and revenue > 0:
            results.append({"year_month": year_month, "revenue": float(revenue)})

    return results


def _store_and_compute(symbol: str, records: list[dict]) -> None:
    """Store fetched records and compute YoY/MoM growth rates."""
    _ensure_table()
    with sqlite3.connect(DB_PATH) as con:
        con.executemany(
            "INSERT OR REPLACE INTO monthly_revenue (symbol, year_month, revenue) VALUES (?,?,?)",
            [(symbol, r["year_month"], r["revenue"]) for r in records],
        )

    # Recompute growth rates
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT year_month, revenue FROM monthly_revenue WHERE symbol=? ORDER BY year_month",
            (symbol,),
        ).fetchall()

    rev_map = {r["year_month"]: r["revenue"] for r in rows}
    updates = []
    for ym, rev in rev_map.items():
        y, m = int(ym[:4]), int(ym[5:7])
        prev_year = f"{y-1}-{m:02d}"
        yoy = None
        if prev_year in rev_map and rev_map[prev_year] > 0:
            yoy = round((rev - rev_map[prev_year]) / rev_map[prev_year] * 100, 2)
        pm, py = m - 1, y
        if pm == 0:
            pm, py = 12, y - 1
        prev_month = f"{py}-{pm:02d}"
        mom = None
        if prev_month in rev_map and rev_map[prev_month] > 0:
            mom = round((rev - rev_map[prev_month]) / rev_map[prev_month] * 100, 2)
        updates.append((yoy, mom, symbol, ym))

    with sqlite3.connect(DB_PATH) as con:
        con.executemany(
            "UPDATE monthly_revenue SET yoy_pct=?, mom_pct=? WHERE symbol=? AND year_month=?",
            updates,
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/revenue/{symbol}", summary="Monthly revenue history")
def get_revenue(
    symbol: str,
    limit: int = Query(24, ge=1, le=60),
) -> dict:
    """Return stored monthly revenue records for a symbol."""
    _ensure_table()
    sym = symbol.upper()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT year_month, revenue, yoy_pct, mom_pct FROM monthly_revenue "
            "WHERE symbol=? ORDER BY year_month DESC LIMIT ?",
            (sym, limit),
        ).fetchall()

    return {
        "symbol": sym,
        "count": len(rows),
        "data": [dict(r) for r in rows],
    }


@router.post("/revenue/{symbol}/fetch", summary="Fetch monthly revenue from FinMind")
def fetch_revenue(
    symbol: str,
    months: int = Query(24, ge=1, le=48, description="Approximate months of history"),
) -> dict:
    """Trigger a fetch from FinMind and store results."""
    sym = symbol.upper()
    import datetime
    start_year = datetime.date.today().year - (months // 12 + 2)
    start_date = f"{start_year}-01-01"

    try:
        records = _fetch_finmind_revenue(sym, start_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not records:
        raise HTTPException(status_code=404, detail=f"No revenue data found for {sym} from FinMind")

    _store_and_compute(sym, records)
    return {
        "symbol": sym,
        "fetched": len(records),
        "records": records[-3:],  # return last 3 as sample
    }


@router.get("/revenue", summary="Revenue for multiple symbols")
def get_revenue_multi(
    symbols: str = Query(..., description="Comma-separated symbols e.g. 2330,2317"),
    limit: int = Query(12, ge=1, le=36),
) -> dict:
    """Return latest N months of revenue for multiple symbols."""
    _ensure_table()
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    result = {}
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        for sym in sym_list:
            rows = con.execute(
                "SELECT year_month, revenue, yoy_pct, mom_pct FROM monthly_revenue "
                "WHERE symbol=? ORDER BY year_month DESC LIMIT ?",
                (sym, limit),
            ).fetchall()
            result[sym] = [dict(r) for r in rows]
    return result
