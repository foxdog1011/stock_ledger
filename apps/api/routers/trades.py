"""Trade endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ..schemas import AddTradeIn
from ledger import StockLedger

router = APIRouter()


@router.post("/trades", status_code=201, summary="Record a buy or sell trade")
def add_trade(body: AddTradeIn, ledger: StockLedger = Depends(get_ledger)):
    """
    Record a stock trade.

    Cash is automatically adjusted:
    - **buy**  → cash -= qty × price + commission
    - **sell** → cash += qty × price − commission

    Returns 400 if cash or share balance is insufficient.
    """
    try:
        ledger.add_trade(
            symbol=body.symbol,
            side=body.side,
            qty=body.qty,
            price=body.price,
            date=body.date,
            commission=body.commission,
            tax=body.tax,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cash_after = ledger.cash_balance(as_of=body.date)
    qty_after = ledger.position(body.symbol, as_of=body.date)
    return {
        "symbol": body.symbol.upper(),
        "side": body.side,
        "qty": body.qty,
        "price": body.price,
        "commission": body.commission,
        "tax": body.tax,
        "date": body.date,
        "note": body.note,
        "cash_after": cash_after,
        "position_after": qty_after,
    }


@router.get("/trades", summary="List trade history")
def list_trades(
    symbol: Optional[str] = Query(None, description="Filter by ticker (optional)"),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    include_void: bool = Query(False, description="Include voided trades (is_void=1)"),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    """
    Return trade records, optionally filtered by symbol and/or date range.

    Voided trades are **excluded** by default.
    Pass `include_void=true` to see them (they carry `is_void: 1`).
    """
    return ledger.trade_history(
        symbol=symbol, start=start, end=end, include_void=include_void
    )


@router.patch(
    "/trades/{trade_id}/void",
    summary="Void (soft-delete) a trade",
)
def void_trade(trade_id: int, ledger: StockLedger = Depends(get_ledger)):
    """
    Mark a trade as voided.

    Voided trades are **excluded** from all P&L, position, cash-balance,
    and equity calculations.  The record remains in the database for audit
    purposes and is returned when `include_void=true` is passed to
    `GET /api/trades`.

    Returns **404** if the trade id does not exist.
    Returns **400** if the trade is already voided.
    """
    try:
        ledger.void_trade(trade_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    return {"id": trade_id, "is_void": 1}
