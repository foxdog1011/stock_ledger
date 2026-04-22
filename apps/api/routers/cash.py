"""Cash endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ..schemas import AddCashIn, CashBalanceOut, CashTxOut, PageParams, paginate
from ledger import StockLedger

router = APIRouter()


@router.post("/cash", status_code=201, summary="Add a cash deposit or withdrawal")
def add_cash(body: AddCashIn, ledger: StockLedger = Depends(get_ledger)):
    """
    Record a manual cash movement.

    - `amount > 0` → deposit
    - `amount < 0` → withdrawal
    """
    try:
        ledger.add_cash(amount=body.amount, date=body.date, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    balance = ledger.cash_balance(as_of=body.date)
    return {"date": body.date, "amount": body.amount, "note": body.note, "balance": balance}


@router.get("/cash/balance", response_model=CashBalanceOut, summary="Query cash balance")
def cash_balance(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD  (default: today)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Return the cash balance as of a given date.

    Includes the cash impact of all trades on or before that date.
    """
    balance = ledger.cash_balance(as_of=as_of)
    from datetime import date
    return CashBalanceOut(as_of=as_of or str(date.today()), balance=balance)


@router.get("/cash/tx", summary="List cash flow statement")
def cash_tx(
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    include_void: bool = Query(False, description="Include voided cash entries"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(0, ge=0, description="Items per page (0 = return all)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Return all cash movements (manual deposits/withdrawals **and** trade impacts)
    sorted by date.

    Each entry carries an absolute `balance` field (running total from the
    very first recorded transaction).  Voided cash entries are excluded by
    default; pass ``include_void=true`` to see them.

    **Pagination**: pass `page` and `page_size` to paginate results.
    When `page_size=0` (default), all results are returned as a plain list
    for backward compatibility.
    """
    rows = ledger.cash_flow(start=start, end=end, include_void=include_void)
    return paginate(rows, PageParams(page=page, page_size=page_size))


@router.patch("/cash/{cash_id}/void", summary="Void (soft-delete) a cash entry")
def void_cash(cash_id: int, ledger: StockLedger = Depends(get_ledger)):
    """
    Mark a manual cash entry as voided.

    The entry is excluded from all future cash-balance and equity calculations.
    The record is kept for audit purposes and returned when ``include_void=true``
    is passed to ``GET /api/cash/tx``.

    Returns **404** if the cash entry id does not exist.
    Returns **400** if the entry is already voided.
    """
    try:
        ledger.void_cash(cash_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc))
    return {"id": cash_id, "is_void": 1}
