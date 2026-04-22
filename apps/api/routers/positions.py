"""Positions endpoint."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ..schemas import PageParams, PositionOut, paginate
from ledger import StockLedger

router = APIRouter()


@router.get(
    "/positions",
    summary="Current positions with avg cost and P&L",
)
def get_positions(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD  (default: today)"),
    include_closed: bool = Query(False, description="Include fully-closed positions"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(0, ge=0, description="Items per page (0 = return all)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Return all **open** positions as of `as_of` (default today), enriched with:

    - `avg_cost`       – weighted average cost per share (includes buy commission)
    - `realized_pnl`   – cumulative gain from partial / full sells of this symbol
    - `unrealized_pnl` – (last_price − avg_cost) × qty
    - `price_source`   – `"quote"` (from `add_price`) or `"trade_fallback"`

    Set `include_closed=true` to also see fully-sold positions
    (qty = 0 but realized_pnl may be non-zero).

    **Pagination**: pass `page` and `page_size` to paginate results.
    When `page_size=0` (default), all results are returned as a plain list
    for backward compatibility.
    """
    rows = ledger.all_positions_pnl(as_of=as_of, open_only=not include_closed)
    return paginate(rows, PageParams(page=page, page_size=page_size))


@router.get("/positions/detail", summary="Extended position detail with WAC history")
def get_positions_detail(
    as_of: Optional[str] = Query(None),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    try:
        syms = ledger.positions(as_of=as_of)
        return [ledger.position_detail(sym, as_of=as_of) for sym in syms]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
