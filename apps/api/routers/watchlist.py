"""Watchlist endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


# ── request models ────────────────────────────────────────────────────────────

class CreateWatchlistIn(BaseModel):
    name: str
    description: str = ""


class AddWatchlistItemIn(BaseModel):
    symbol: str
    industry_position: str = ""
    operation_focus: str = ""
    thesis_summary: str = ""
    primary_catalyst: str = ""
    status: str = "watching"


class UpdateWatchlistItemIn(BaseModel):
    industry_position: str | None = None
    operation_focus: str | None = None
    thesis_summary: str | None = None
    primary_catalyst: str | None = None
    status: str | None = None


# ── watchlists ────────────────────────────────────────────────────────────────

@router.post("/watchlist/lists", summary="Create a watchlist")
def create_watchlist(
    body: CreateWatchlistIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.watchlist.repository import create_watchlist as _create
    try:
        return _create(ledger.db_path, body.name, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/watchlist/lists", summary="List all watchlists")
def list_watchlists(
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.watchlist.repository import list_watchlists as _list
    return _list(ledger.db_path)


# ── watchlist items ───────────────────────────────────────────────────────────

@router.post(
    "/watchlist/lists/{watchlist_id}/items",
    summary="Add a symbol to a watchlist",
)
def add_watchlist_item(
    watchlist_id: int,
    body: AddWatchlistItemIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.watchlist.repository import add_watchlist_item as _add
    try:
        return _add(
            ledger.db_path, watchlist_id, body.symbol,
            body.industry_position, body.operation_focus,
            body.thesis_summary, body.primary_catalyst, body.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/watchlist/lists/{watchlist_id}/items",
    summary="List items in a watchlist",
)
def list_watchlist_items(
    watchlist_id: int,
    include_archived: bool = Query(False),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.watchlist.repository import list_watchlist_items as _list
    return _list(ledger.db_path, watchlist_id, include_archived=include_archived)


@router.patch(
    "/watchlist/lists/{watchlist_id}/items/{item_id}",
    summary="Update a watchlist item",
)
def update_watchlist_item(
    watchlist_id: int,
    item_id: int,
    body: UpdateWatchlistItemIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.watchlist.repository import update_watchlist_item as _update
    try:
        result = _update(
            ledger.db_path, item_id, body.model_dump(exclude_none=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return result


# ── coverage & gaps ───────────────────────────────────────────────────────────

@router.get(
    "/watchlist/lists/{watchlist_id}/coverage",
    summary="3x coverage check for a watchlist",
)
def get_coverage(
    watchlist_id: int,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.watchlist.service import get_watchlist_coverage
    try:
        return get_watchlist_coverage(ledger.db_path, watchlist_id, ledger)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/watchlist/lists/{watchlist_id}/gaps",
    summary="Coverage gap analysis for a watchlist",
)
def get_gaps(
    watchlist_id: int,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.watchlist.service import list_watchlist_gaps
    try:
        return list_watchlist_gaps(ledger.db_path, watchlist_id, ledger)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
