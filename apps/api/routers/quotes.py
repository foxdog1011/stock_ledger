"""Quote / price endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ..schemas import AddPriceIn, LastPriceOut
from ledger import StockLedger

router = APIRouter()


@router.post("/quotes/manual", status_code=201, summary="Add a manual closing price")
def add_price(body: AddPriceIn, ledger: StockLedger = Depends(get_ledger)):
    """
    Insert or replace a daily closing price for a symbol.

    Used for mark-to-market when live price feeds are not available.
    If a price for `(symbol, date)` already exists it is overwritten (upsert).
    """
    try:
        ledger.add_price(symbol=body.symbol, date=body.date, close=body.close)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"symbol": body.symbol.upper(), "date": body.date, "close": body.close}


@router.get(
    "/quotes/last",
    response_model=LastPriceOut,
    summary="Query the latest available price for a symbol",
)
def last_price(
    symbol: str = Query(..., description="Ticker symbol, e.g. '2330'"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD  (default: today)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Return the most recent price on or before `as_of`.

    **Price discovery order:**
    1. `prices` table – entries added via `POST /api/quotes/manual`
    2. Last trade price for the symbol (`price_source: "trade_fallback"`)

    Returns `price: null` if no price information is available.
    """
    result = ledger.last_price_with_source(symbol=symbol, as_of=as_of)
    return LastPriceOut(**result)
