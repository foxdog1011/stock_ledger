"""Performance summary and risk metrics endpoints."""
from __future__ import annotations

import math
import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


def _daily_data(ledger: StockLedger, start: str, end: str) -> list[dict]:
    return ledger.daily_equity(start=start, end=end, freq="B")


@router.get("/perf/summary", summary="Performance summary for a date range")
def perf_summary(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Aggregate performance metrics between *start* and *end*.

    | field                  | description                                          |
    |------------------------|------------------------------------------------------|
    | start_equity           | total equity on start date                           |
    | end_equity             | total equity on end date                             |
    | external_cashflow_sum  | net external cash injected / withdrawn               |
    | pnl_ex_cashflow        | end − start − external_cashflow (pure investment P&L)|
    | realized_pnl           | incremental realized gain in the period              |
    | unrealized_pnl         | unrealized gain at end date                          |
    | fees_total             | commission + tax in the period                       |
    | fees_commission        | commissions paid                                     |
    | fees_tax               | taxes paid                                           |
    """
    daily = _daily_data(ledger, start, end)
    if not daily:
        return {
            "start_equity": None,
            "end_equity": None,
            "external_cashflow_sum": 0,
            "pnl_ex_cashflow": None,
            "realized_pnl": None,
            "unrealized_pnl": None,
            "fees_total": None,
            "fees_commission": None,
            "fees_tax": None,
        }

    start_equity = daily[0]["total_equity"]
    end_equity = daily[-1]["total_equity"]
    external_cashflow_sum = sum(d["external_cashflow"] for d in daily)
    pnl_ex_cashflow = end_equity - start_equity - external_cashflow_sum

    # Fees from trades in range
    db_path = str(ledger._db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT SUM(commission) AS c, SUM(tax) AS t FROM trades"
            " WHERE date >= ? AND date <= ? AND is_void = 0",
            (start, end),
        ).fetchone()
    fees_commission = float(row["c"] or 0)
    fees_tax = float(row["t"] or 0)
    fees_total = fees_commission + fees_tax

    # Realized / unrealized P&L
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    try:
        start_pos = ledger.all_positions_pnl(as_of=start, open_only=False)
        end_pos = ledger.all_positions_pnl(as_of=end, open_only=False)
        unrealized_pnl = sum(
            p["unrealized_pnl"] for p in end_pos if p.get("unrealized_pnl") is not None
        )
        realized_end = sum(p.get("realized_pnl", 0) for p in end_pos)
        realized_start = sum(p.get("realized_pnl", 0) for p in start_pos)
        realized_pnl = realized_end - realized_start
    except Exception:
        pass

    return {
        "start_equity": start_equity,
        "end_equity": end_equity,
        "external_cashflow_sum": external_cashflow_sum,
        "pnl_ex_cashflow": pnl_ex_cashflow,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "fees_total": fees_total,
        "fees_commission": fees_commission,
        "fees_tax": fees_tax,
    }


@router.get("/risk/metrics", summary="Risk metrics for a date range")
def risk_metrics(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Risk / return statistics derived from daily business-day returns.

    | field                | description                                   |
    |----------------------|-----------------------------------------------|
    | sharpe_ratio         | annualised Sharpe (risk-free = 0)             |
    | positive_day_ratio   | % of days with positive return                |
    | worst_day_pct        | worst single-day return (%)                   |
    | best_day_pct         | best single-day return (%)                    |
    | trading_days         | number of business days with valid returns    |
    | avg_daily_return_pct | arithmetic mean of daily returns              |
    | volatility_pct       | std-dev of daily returns                      |
    """
    daily = _daily_data(ledger, start, end)
    returns = [d["daily_return_pct"] for d in daily if d.get("daily_return_pct") is not None]

    if not returns:
        return {
            "sharpe_ratio": None,
            "positive_day_ratio": None,
            "worst_day_pct": None,
            "best_day_pct": None,
            "trading_days": 0,
            "avg_daily_return_pct": None,
            "volatility_pct": None,
        }

    n = len(returns)
    avg = sum(returns) / n
    variance = sum((r - avg) ** 2 for r in returns) / n if n > 1 else 0.0
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    sharpe: float | None = None
    if std_dev > 0:
        sharpe = round((avg / std_dev) * math.sqrt(252), 4)

    positive_days = sum(1 for r in returns if r > 0)

    return {
        "sharpe_ratio": sharpe,
        "positive_day_ratio": round(positive_days / n * 100, 2),
        "worst_day_pct": round(min(returns), 4),
        "best_day_pct": round(max(returns), 4),
        "trading_days": n,
        "avg_daily_return_pct": round(avg, 4),
        "volatility_pct": round(std_dev, 4),
    }
