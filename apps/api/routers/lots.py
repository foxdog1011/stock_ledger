"""Lot-level endpoint (FIFO / LIFO / WAC)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


@router.get("/lots", summary="Lot-level position detail")
def get_lots(
    symbol: str = Query(...),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD"),
    method: str = Query("fifo", description="fifo | lifo | wac"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    try:
        return ledger.lots_by_method(symbol=symbol, as_of=as_of, method=method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
