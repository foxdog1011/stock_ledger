"""Daily equity endpoint."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

_VALID_FREQS = {"D", "B"}
_VALID_MODES = {"delta", "pnl"}


@router.get("/equity/daily", summary="Daily equity and P&L records")
def equity_daily(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    mode: str = Query(
        "pnl",
        description=(
            "delta = daily_change including external cashflows; "
            "pnl = daily_pnl excluding external cashflows"
        ),
    ),
    freq: str = Query("B", description="D = every calendar day, B = business days (Mon–Fri)"),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    """
    Return one record per day in `[start, end]`.

    | field                  | description                                              |
    |------------------------|----------------------------------------------------------|
    | date                   | ISO date                                                 |
    | cash                   | cash balance                                             |
    | market_value           | portfolio market value                                   |
    | total_equity           | cash + market_value                                      |
    | external_cashflow      | net cash deposits / withdrawals that day                 |
    | daily_change           | total_equity_today − total_equity_yesterday (incl. cash) |
    | daily_pnl              | daily_change − external_cashflow (pure P&L)              |
    | daily_return_pct       | daily_pnl / equity_yesterday × 100 (null if base = 0)   |
    | price_staleness_days   | days since most recent quote (0 = fresh, null = no quote)|
    | used_quote_date_map    | {symbol: last_quote_date}                                |
    """
    if freq not in _VALID_FREQS:
        raise HTTPException(
            status_code=422,
            detail=f"freq must be one of {sorted(_VALID_FREQS)}, got '{freq}'",
        )
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode must be one of {sorted(_VALID_MODES)}, got '{mode}'",
        )
    try:
        return ledger.daily_equity(start=start, end=end, freq=freq)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
