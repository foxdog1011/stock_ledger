"""Rebalance check endpoint."""
from __future__ import annotations

import sqlite3
from datetime import date as Date, datetime

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

# Default thresholds (hardcoded; a future /settings endpoint can override these)
_SINGLE_LIMIT_PCT: float = 40.0
_TOP3_LIMIT_PCT: float = 70.0
_CASH_HIGH_PCT: float = 50.0
_STALE_QUOTES_DAYS: int = 2


@router.get("/rebalance/check", summary="Portfolio rebalance alerts")
def rebalance_check(
    as_of: str = Query(default=None, description="YYYY-MM-DD (defaults to today)"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Evaluate the portfolio against concentration and staleness thresholds.

    Default thresholds
    ------------------
    - single_position_limit_pct = 40  (warn if any one stock > 40 % of portfolio)
    - top3_limit_pct             = 70  (warn if top-3 stocks > 70 %)
    - cash_high_pct              = 50  (info if cash > 50 %)
    - stale_quotes_days          = 2   (warn if quote older than 2 days)

    Returns
    -------
    ```json
    {
      "alerts": [{"type", "severity", "message", "data"}, ...],
      "metrics": {"cash_pct", "top1_pct", "top3_pct"}
    }
    ```
    """
    if as_of is None:
        as_of = str(Date.today())

    snap = ledger.equity_snapshot(as_of=as_of)
    total_equity: float = snap["total_equity"]
    cash: float = snap["cash"]
    positions: dict = snap["positions"]  # {symbol: {qty, price, market_value}}

    if total_equity <= 0:
        return {"alerts": [], "metrics": {"cash_pct": 0.0, "top1_pct": 0.0, "top3_pct": 0.0}}

    cash_pct = cash / total_equity * 100

    sorted_pos = sorted(
        [(sym, float(p.get("market_value") or 0)) for sym, p in positions.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    top1_pct = (sorted_pos[0][1] / total_equity * 100) if sorted_pos else 0.0
    top3_pct = (sum(v for _, v in sorted_pos[:3]) / total_equity * 100) if sorted_pos else 0.0

    alerts: list[dict] = []

    # Single-position concentration
    for sym, mv in sorted_pos:
        pct = mv / total_equity * 100
        if pct > _SINGLE_LIMIT_PCT:
            alerts.append(
                {
                    "type": "concentration",
                    "severity": "warning",
                    "message": (
                        f"{sym} is {pct:.1f}% of portfolio "
                        f"(limit: {_SINGLE_LIMIT_PCT:.0f}%)"
                    ),
                    "data": {"symbol": sym, "pct": round(pct, 2)},
                }
            )

    # Top-3 concentration
    if top3_pct > _TOP3_LIMIT_PCT:
        top3_syms = [s for s, _ in sorted_pos[:3]]
        alerts.append(
            {
                "type": "top3_concentration",
                "severity": "info",
                "message": (
                    f"Top 3 ({', '.join(top3_syms)}) = {top3_pct:.1f}% "
                    f"(limit: {_TOP3_LIMIT_PCT:.0f}%)"
                ),
                "data": {"symbols": top3_syms, "pct": round(top3_pct, 2)},
            }
        )

    # High cash
    if cash_pct > _CASH_HIGH_PCT:
        alerts.append(
            {
                "type": "high_cash",
                "severity": "info",
                "message": (
                    f"Cash is {cash_pct:.1f}% of portfolio "
                    f"(limit: {_CASH_HIGH_PCT:.0f}%)"
                ),
                "data": {"cash_pct": round(cash_pct, 2)},
            }
        )

    # Stale quotes
    db_path = str(ledger._db_path)
    stale_syms: list[str] = []
    as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").date()
    for sym in positions:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT date FROM prices WHERE symbol=? AND date<=?"
                " ORDER BY date DESC LIMIT 1",
                (sym, as_of),
            ).fetchone()
        if row is None:
            stale_syms.append(sym)
        else:
            quote_dt = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if (as_of_dt - quote_dt).days > _STALE_QUOTES_DAYS:
                stale_syms.append(sym)

    if stale_syms:
        alerts.append(
            {
                "type": "stale_quotes",
                "severity": "warning",
                "message": f"Stale/missing quotes for: {', '.join(stale_syms)}",
                "data": {"symbols": stale_syms},
            }
        )

    return {
        "alerts": alerts,
        "metrics": {
            "cash_pct": round(cash_pct, 2),
            "top1_pct": round(top1_pct, 2),
            "top3_pct": round(top3_pct, 2),
        },
    }
