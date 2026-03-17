"""Execution simulation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


@router.get("/execution/offset/losing", summary="List all open losing positions")
def offset_losing(
    as_of: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.execution.offsetting import losing_positions
    return losing_positions(ledger, as_of=as_of)


@router.get("/execution/offset/profit-inventory", summary="Realized P&L available to offset")
def offset_profit_inventory(
    as_of: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.execution.offsetting import profit_inventory
    return profit_inventory(ledger, as_of=as_of)


@router.get("/execution/offset/simulate/{symbol}", summary="Simulate offsetting a losing position")
def offset_simulate(
    symbol: str,
    qty: float | None = Query(None, description="Shares to sell; defaults to full position"),
    price: float | None = Query(None, description="Sell price; defaults to last_price"),
    as_of: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.execution.offsetting import simulate_offsetting
    return simulate_offsetting(ledger, symbol=symbol, qty=qty, price=price, as_of=as_of)
