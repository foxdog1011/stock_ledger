"""Universe endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


# ── request models ────────────────────────────────────────────────────────────

class AddCompanyIn(BaseModel):
    symbol: str
    name: str
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    business_model: str | None = None
    country: str | None = None
    currency: str | None = None
    note: str = ""


class UpdateCompanyIn(BaseModel):
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    business_model: str | None = None
    country: str | None = None
    currency: str | None = None
    note: str | None = None


class AddRelationshipIn(BaseModel):
    related_symbol: str
    relationship_type: str
    note: str = ""


class AddThesisIn(BaseModel):
    thesis_type: str
    content: str


# ── company master ────────────────────────────────────────────────────────────

@router.post("/universe/companies", summary="Add a company to the universe")
def add_company(
    body: AddCompanyIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.universe.repository import add_company as _add
    try:
        return _add(ledger.db_path, **body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/universe/companies", summary="List all companies in the universe")
def list_companies(
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.universe.repository import list_companies as _list
    return _list(ledger.db_path)


@router.get("/universe/companies/{symbol}", summary="Get full company detail")
def get_company(
    symbol: str,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.universe.service import get_company_detail
    result = get_company_detail(ledger.db_path, symbol)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Company '{symbol.upper()}' not found")
    return result


@router.put("/universe/companies/{symbol}", summary="Update company master fields")
def update_company(
    symbol: str,
    body: UpdateCompanyIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.universe.repository import update_company as _update
    result = _update(ledger.db_path, symbol, body.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Company '{symbol.upper()}' not found")
    return result


# ── relationships ─────────────────────────────────────────────────────────────

@router.post(
    "/universe/companies/{symbol}/relationships",
    summary="Add a relationship for a company",
)
def add_relationship(
    symbol: str,
    body: AddRelationshipIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.universe.repository import add_relationship as _add
    try:
        return _add(
            ledger.db_path, symbol,
            body.related_symbol, body.relationship_type, body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/universe/companies/{symbol}/relationships",
    summary="List relationships for a company",
)
def list_relationships(
    symbol: str,
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.universe.repository import list_relationships as _list
    return _list(ledger.db_path, symbol)


# ── thesis ────────────────────────────────────────────────────────────────────

@router.post(
    "/universe/companies/{symbol}/thesis",
    summary="Add a thesis entry for a company",
)
def add_thesis(
    symbol: str,
    body: AddThesisIn,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.universe.repository import add_thesis as _add
    try:
        return _add(ledger.db_path, symbol, body.thesis_type, body.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/universe/companies/{symbol}/thesis",
    summary="List thesis entries for a company",
)
def list_thesis(
    symbol: str,
    active_only: bool = Query(True, description="If true, return only active entries"),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    from domain.universe.repository import list_thesis as _list
    return _list(ledger.db_path, symbol, active_only=active_only)


@router.delete(
    "/universe/thesis/{thesis_id}",
    status_code=204,
    summary="Soft-delete (deactivate) a thesis entry",
)
def deactivate_thesis(
    thesis_id: int,
    ledger: StockLedger = Depends(get_ledger),
) -> None:
    from domain.universe.repository import deactivate_thesis as _deactivate
    try:
        _deactivate(ledger.db_path, thesis_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
