"""Trade endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ..config import AUTO_REFRESH_QUOTES_ON_TRADE, QUOTE_PROVIDER
from ..deps import get_ledger
from ..schemas import AddTradeIn, paginate
from ledger import StockLedger

router = APIRouter()
logger = logging.getLogger(__name__)


def _bg_refresh_for_trade(symbol: str, as_of: str, ledger: StockLedger) -> None:
    """Background task: fetch a quote for *symbol* on *as_of* after a new trade."""
    try:
        from ..services.quotes_service import refresh_quotes_for_symbols
        result = refresh_quotes_for_symbols(
            ledger=ledger,
            symbols=[symbol],
            as_of=as_of,
            provider_name=QUOTE_PROVIDER,
            trigger="trade",
            skip_if_fresh=True,
            max_age_days=2,
        )
        logger.info(
            "Trade-triggered refresh: symbol=%s as_of=%s inserted=%d skipped=%d errors=%d",
            symbol, as_of, result.inserted, result.skipped, len(result.errors),
        )
    except Exception:
        logger.exception("Trade-triggered refresh failed for %s", symbol)


@router.post("/trades", status_code=201, summary="Record a buy or sell trade")
def add_trade(
    body: AddTradeIn,
    background_tasks: BackgroundTasks,
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Record a stock trade.

    Cash is automatically adjusted:
    - **buy**  → cash -= qty × price + commission
    - **sell** → cash += qty × price − commission

    Returns 400 if cash or share balance is insufficient.

    When `AUTO_REFRESH_QUOTES_ON_TRADE=1` (default), a background task is
    queued to fetch the latest closing price for the traded symbol.
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

    # Auto-refresh quote in background (non-blocking)
    if AUTO_REFRESH_QUOTES_ON_TRADE:
        background_tasks.add_task(
            _bg_refresh_for_trade,
            symbol=body.symbol.upper(),
            as_of=body.date,
            ledger=ledger,
        )

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
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(0, ge=0, description="Items per page (0 = return all)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Return trade records, optionally filtered by symbol and/or date range.

    Voided trades are **excluded** by default.
    Pass `include_void=true` to see them (they carry `is_void: 1`).

    **Pagination**: pass `page` and `page_size` to paginate results.
    When `page_size=0` (default), all results are returned as a plain list
    for backward compatibility.
    """
    from ..schemas import PageParams

    rows = ledger.trade_history(
        symbol=symbol, start=start, end=end, include_void=include_void,
    )
    return paginate(rows, PageParams(page=page, page_size=page_size))


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
