"""Jimmy-style Rolling Position Log + Sector Rotation Alert.

Based on Jimmy Kuan-Yu Chen's trading methodology:
- Rolling a Position: realize 0.5-1% profit daily, reopen to maintain exposure
- Adjusted Risk: track how much original capital is still at risk
- Sector Rotation: alert when portfolio is over-concentrated in one sector
"""
from __future__ import annotations

import sqlite3
from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_ledger
from ..config import DB_PATH
from ledger import StockLedger

router = APIRouter()


# ── Schema ─────────────────────────────────────────────────────────────────────

class RollingLogIn(BaseModel):
    date: str                    # YYYY-MM-DD
    symbol: str
    action: str                  # "roll" | "realize" | "reopen" | "note"
    shares: Optional[float] = None
    sell_price: Optional[float] = None
    buy_price: Optional[float] = None
    profit_amount: Optional[float] = None  # realized profit this roll
    note: str = ""


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _ensure_table(db_path: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS rolling_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                date           TEXT    NOT NULL,
                symbol         TEXT    NOT NULL,
                action         TEXT    NOT NULL,  -- roll | realize | reopen | note
                shares         REAL,
                sell_price     REAL,
                buy_price      REAL,
                profit_amount  REAL,
                note           TEXT    DEFAULT '',
                created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/rolling", status_code=201, summary="Log a rolling position action")
def create_rolling_log(body: RollingLogIn):
    """
    Record a Jimmy-style rolling action.

    Action types:
    - **roll**: Full cycle — sell high, buy back lower (or same day)
    - **realize**: Partial profit-taking without full close
    - **reopen**: Reopen after a sell (buy back in)
    - **note**: Free-form observation without a trade
    """
    if body.action not in ("roll", "realize", "reopen", "note"):
        raise HTTPException(status_code=400, detail="action must be 'roll', 'realize', 'reopen', or 'note'")

    _ensure_table(DB_PATH)
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """INSERT INTO rolling_log
               (date, symbol, action, shares, sell_price, buy_price, profit_amount, note)
               VALUES (?,?,?,?,?,?,?,?)""",
            (body.date, body.symbol.upper(), body.action,
             body.shares, body.sell_price, body.buy_price,
             body.profit_amount, body.note),
        )
        return {
            "id": cur.lastrowid,
            "date": body.date,
            "symbol": body.symbol.upper(),
            "action": body.action,
            "profit_amount": body.profit_amount,
        }


@router.get("/rolling", summary="List rolling position log")
def list_rolling_log(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    start:  Optional[str] = Query(None, description="YYYY-MM-DD"),
    end:    Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit:  int            = Query(50, description="Max rows to return"),
):
    _ensure_table(DB_PATH)
    conditions = []
    params: list = []
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol.upper())
    if start:
        conditions.append("date >= ?")
        params.append(start)
    if end:
        conditions.append("date <= ?")
        params.append(end)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"SELECT * FROM rolling_log {where} ORDER BY date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/rolling/summary", summary="Rolling P&L summary")
def rolling_summary(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
):
    """
    Aggregate rolling profit statistics.

    Returns total realized profit from rolling actions, count of rolls,
    and average profit per roll — the core metrics for Jimmy's strategy.
    """
    _ensure_table(DB_PATH)
    conditions = ["profit_amount IS NOT NULL"]
    params: list = []
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol.upper())
    where = "WHERE " + " AND ".join(conditions)

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"""SELECT symbol,
                       COUNT(*)                        AS roll_count,
                       SUM(profit_amount)              AS total_profit,
                       AVG(profit_amount)              AS avg_profit,
                       MAX(date)                       AS last_roll_date
                FROM rolling_log {where}
                GROUP BY symbol
                ORDER BY total_profit DESC""",
            params,
        ).fetchall()

    totals = con.execute(
        f"""SELECT COUNT(*)       AS total_rolls,
                   SUM(profit_amount) AS grand_total_profit
            FROM rolling_log {where}""",
        params,
    ) if False else None  # already closed — re-query below

    with sqlite3.connect(DB_PATH) as con:
        agg = con.execute(
            f"""SELECT COUNT(*)           AS total_rolls,
                       COALESCE(SUM(profit_amount), 0) AS grand_total_profit
                FROM rolling_log {where}""",
            params,
        ).fetchone()

    return {
        "grand_total_profit": round(agg[1], 2),
        "total_rolls": agg[0],
        "by_symbol": [dict(r) for r in rows],
    }


@router.get("/rolling/sector-check", summary="Sector concentration (Sector Rotation alert)")
def sector_check(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Check sector concentration across current holdings.

    Jimmy's rule: positions must span **completely different sectors**.
    With 3 positions you should have 3 different sectors.
    Any sector exceeding 50% of portfolio value triggers a warning.

    Returns sector breakdown + alert flag.
    """
    date_str = as_of or str(Date.today())
    snap = ledger.equity_snapshot(as_of=date_str)
    positions = snap.get("positions", {})

    if not positions:
        return {"alert": False, "message": "No open positions", "sectors": []}

    # Fetch sector data from universe
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        companies = {
            row["symbol"]: row
            for row in con.execute(
                "SELECT symbol, name, sector, industry FROM company_master"
            ).fetchall()
        }

    # Build sector → market_value map
    sector_map: dict[str, dict] = {}
    unknown_symbols = []

    total_mv = 0.0
    for sym, pos in positions.items():
        mv = pos.get("market_value") or 0.0
        total_mv += mv
        company = companies.get(sym)
        sector = company["sector"] if company and company["sector"] else "未分類"
        if not company:
            unknown_symbols.append(sym)
        if sector not in sector_map:
            sector_map[sector] = {"sector": sector, "symbols": [], "market_value": 0.0}
        sector_map[sector]["symbols"].append(sym)
        sector_map[sector]["market_value"] += mv

    # Calculate percentages + build output
    sectors_out = []
    alerts = []
    for s in sorted(sector_map.values(), key=lambda x: -x["market_value"]):
        pct = round(s["market_value"] / total_mv * 100, 1) if total_mv > 0 else 0.0
        s["pct_of_portfolio"] = pct
        s["market_value"] = round(s["market_value"], 2)
        sectors_out.append(s)
        if pct > 50:
            alerts.append(f"{s['sector']} 占 {pct}% — 超過 50% 集中警示")

    # Additional: check if all positions in same sector
    unique_sectors = len(sector_map)
    total_positions = len(positions)
    if unique_sectors < total_positions and total_positions >= 3:
        alerts.append(
            f"持有 {total_positions} 檔，但只涵蓋 {unique_sectors} 個產業 "
            f"— Jimmy 建議每檔應在完全不同的產業"
        )

    return {
        "as_of": date_str,
        "alert": len(alerts) > 0,
        "alerts": alerts,
        "unique_sectors": unique_sectors,
        "total_positions": total_positions,
        "total_market_value": round(total_mv, 2),
        "sectors": sectors_out,
        "unknown_symbols": unknown_symbols,
    }


@router.delete("/rolling/{log_id}", summary="Delete a rolling log entry")
def delete_rolling_log(log_id: int):
    _ensure_table(DB_PATH)
    with sqlite3.connect(DB_PATH) as con:
        affected = con.execute(
            "DELETE FROM rolling_log WHERE id = ?", (log_id,)
        ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail=f"Log entry {log_id} not found")
        return {"deleted": log_id}
