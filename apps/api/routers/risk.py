"""Risk endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


@router.get("/risk/positions", summary="Adjusted cost-basis risk view for all positions")
def risk_positions(
    as_of: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    open_only: bool = Query(True, description="If true, return only open positions (risk_free or at_risk)"),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.risk.adjusted import all_positions_adjusted_risk
    return all_positions_adjusted_risk(ledger, as_of=as_of, open_only=open_only)


@router.get("/risk/positions/{symbol}", summary="Adjusted cost-basis risk view for one symbol")
def risk_position(
    symbol: str,
    as_of: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.risk.adjusted import position_adjusted_risk
    return position_adjusted_risk(ledger, symbol=symbol, as_of=as_of)
