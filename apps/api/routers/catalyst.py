"""Catalyst and scenario endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


# ── request models ────────────────────────────────────────────────────────────

class CreateCatalystIn(BaseModel):
    event_type: str
    title: str
    symbol: str | None = None
    event_date: str | None = None
    notes: str = ""


class UpdateCatalystIn(BaseModel):
    title: str | None = None
    event_date: str | None = None
    status: str | None = None
    notes: str | None = None


class UpsertScenarioIn(BaseModel):
    plan_a: str | None = None
    plan_b: str | None = None
    plan_c: str | None = None
    plan_d: str | None = None
    price_target: float | None = None
    stop_loss: float | None = None


# ── catalysts ─────────────────────────────────────────────────────────────────

@router.post("/catalysts", summary="Create a catalyst")
def create_catalyst(
    body: CreateCatalystIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.catalyst.repository import create_catalyst as _create
    try:
        return _create(
            ledger.db_path, body.event_type, body.title,
            symbol=body.symbol, event_date=body.event_date, notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/catalysts/upcoming", summary="Upcoming pending catalysts")
def upcoming_catalysts(
    as_of: str | None = Query(None),
    days: int = Query(30),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.catalyst.service import upcoming_catalysts as _upcoming
    return _upcoming(ledger.db_path, as_of=as_of, days=days)


@router.get("/catalysts", summary="List catalysts")
def list_catalysts(
    symbol: str | None = Query(None),
    status: str | None = Query(None),
    event_type: str | None = Query(None),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.catalyst.repository import list_catalysts as _list
    try:
        return _list(ledger.db_path, symbol=symbol, status=status, event_type=event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/catalysts/{catalyst_id}", summary="Get a catalyst")
def get_catalyst(
    catalyst_id: int,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.catalyst.repository import get_catalyst as _get
    result = _get(ledger.db_path, catalyst_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Catalyst {catalyst_id} not found")
    return result


@router.patch("/catalysts/{catalyst_id}", summary="Update a catalyst")
def update_catalyst(
    catalyst_id: int,
    body: UpdateCatalystIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.catalyst.repository import update_catalyst as _update
    updates = body.model_dump(exclude_none=True)
    try:
        result = _update(ledger.db_path, catalyst_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Catalyst {catalyst_id} not found")
    return result


# ── scenarios ─────────────────────────────────────────────────────────────────

@router.put(
    "/catalysts/{catalyst_id}/scenario",
    summary="Upsert scenario plan for a catalyst",
)
def upsert_scenario(
    catalyst_id: int,
    body: UpsertScenarioIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.scenario.repository import upsert_scenario as _upsert
    updates = body.model_dump(exclude_none=True)
    try:
        return _upsert(ledger.db_path, catalyst_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/catalysts/{catalyst_id}/scenario",
    summary="Get scenario plan for a catalyst",
)
def get_scenario(
    catalyst_id: int,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.scenario.repository import get_scenario as _get
    result = _get(ledger.db_path, catalyst_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No scenario plan for catalyst {catalyst_id}",
        )
    return result
